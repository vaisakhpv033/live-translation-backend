"""Service layer for USV Doctor Detailing LiveKit sessions, webhooks, evaluations, and usage metrics."""

import asyncio
import copy
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from livekit import api

from app.core.config import get_settings
from app.modules.usv_doctor.evaluation import UsvDoctorEvaluationService
from app.modules.usv_doctor.pricing import (
    compute_agent_usage_cost_usd,
    compute_qa_cost_usd,
)
from app.modules.usv_doctor.repository import UsvDoctorReportRepository
from app.modules.usv_doctor.schemas import (
    AgentUsageSummary,
    QAUsageSummary,
    UsvDoctorReportDetail,
    UsvDoctorReportListResponse,
    UsvDoctorReportSummary,
    UsvDoctorSessionCreate,
    UsvDoctorSessionResponse,
    UsvDoctorTokenRequest,
    UsvDoctorWebhookPayload,
)
from app.schemas.room import ParticipantInfo, RoomResponse
from app.schemas.token import TokenResponse

logger = logging.getLogger("translation-agent-backend.modules.usv_doctor.service")
settings = get_settings()


def _generate_usv_room_name(doctor_name: str, specialty: Optional[str] = None) -> str:
    """Generates a dedicated USV Doctor room name: USV-{Specialty}-{Doctor}-{uuid_short}."""
    clean_spec = "".join(ch for ch in (specialty or "Doctor") if ch.isalnum())[:16] or "Doctor"
    clean_doc = "".join(ch for ch in (doctor_name or "Physician") if ch.isalnum())[:18] or "Physician"
    short_id = uuid.uuid4().hex[:6]
    return f"USV-{clean_spec}-{clean_doc}-{short_id}"


def _safe_int(val: Any) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _compute_duration_seconds(started_at: Optional[str], ended_at: Optional[str]) -> int:
    if not started_at or not ended_at:
        return 0
    try:
        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        return max(0, int(round((end_dt - start_dt).total_seconds())))
    except Exception:
        return 0


class UsvDoctorService:
    """Coordinates LiveKit session dispatch, post-call ingestion, QA evaluation, and usage tracking."""

    def __init__(
        self,
        lk_client: Optional[api.LiveKitAPI] = None,
        repository: Optional[UsvDoctorReportRepository] = None,
        evaluation_service: Optional[UsvDoctorEvaluationService] = None,
    ):
        self.client = lk_client
        self.repository = repository
        self.evaluation_service = evaluation_service or UsvDoctorEvaluationService()

    # ──────────────────────────────────────────────────────────
    #  Session Lifecycle (LiveKit Room + ira-voice-agent)
    # ──────────────────────────────────────────────────────────

    async def create_and_dispatch_session(
        self, session_in: UsvDoctorSessionCreate
    ) -> UsvDoctorSessionResponse:
        if self.client is None:
            raise RuntimeError("LiveKitAPI client is required for session creation.")

        doctor_name = (session_in.patient_name or "Dr. Arthur Hayes").strip()
        trainee_id = (session_in.trainee_id or f"REP-{uuid.uuid4().hex[:4]}").strip()
        trainee_name = (session_in.trainee_name or "Medical Sales Representative").strip()

        raw_cfg = (session_in.extra_metadata or {}).get("session_config")
        if isinstance(raw_cfg, str):
            try:
                metadata: Dict[str, Any] = json.loads(raw_cfg)
            except Exception:
                metadata = {}
        elif isinstance(raw_cfg, dict):
            metadata = copy.deepcopy(raw_cfg)
        else:
            metadata = {}

        meta_sub = metadata.setdefault("metadata", {})
        meta_sub.setdefault("scenario", session_in.scenario or "doctor-detailing")
        meta_sub["trainee_id"] = trainee_id
        meta_sub["trainee_name"] = trainee_name
        meta_sub["doctor_name"] = doctor_name
        meta_sub.setdefault("language", session_in.language or "en-IN")

        # Inject reporting webhook configuration for Autocoach-agent ReportingDispatcher
        webhook_url = (
            session_in.reports_webhook_url
            or getattr(settings, "AUTOCOACH_REPORT_WEBHOOK_URL", "")
            or ""
        ).strip()
        if webhook_url:
            reporting_cfg: Dict[str, Any] = {
                "enabled": True,
                "endpoint": {
                    "url": webhook_url,
                    "method": "POST",
                    "timeout_seconds": 10.0,
                },
                "security": {
                    "validate_ssrf": True,
                    "allow_local": bool(getattr(settings, "AUTOCOACH_REPORT_ALLOW_LOCAL", False)),
                },
                "payload_config": {
                    "include_chat_history": True,
                    "include_model_usage": True,
                    "include_events": True,
                },
            }
            webhook_secret = getattr(settings, "AUTOCOACH_REPORT_WEBHOOK_SECRET", "")
            if webhook_secret:
                reporting_cfg["endpoint"]["headers"] = {"X-API-Key": webhook_secret}
            metadata["reporting"] = reporting_cfg

        room_name = _generate_usv_room_name(
            doctor_name=doctor_name,
            specialty=meta_sub.get("doctor_specialty"),
        )
        metadata_json = json.dumps(metadata)

        logger.info(
            f"Creating USV Doctor room '{room_name}' "
            f"(scenario={meta_sub.get('scenario')}, lang={session_in.language}, doctor='{doctor_name}')"
        )
        room_info = await self.client.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                empty_timeout=session_in.empty_timeout or 300,
                max_participants=session_in.max_participants or 5,
                metadata=metadata_json,
            )
        )

        agent_name = session_in.agent_name or "ira-voice-agent"
        try:
            await self.client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room_name,
                    metadata=metadata_json,
                )
            )
        except Exception as exc:
            logger.error(f"Failed dispatching '{agent_name}' to '{room_name}': {exc}", exc_info=True)
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to dispatch agent worker '{agent_name}': {exc}",
            )

        wait_timeout = session_in.wait_timeout_seconds or 10.0
        poll_interval = 0.35
        max_attempts = max(1, int(wait_timeout / poll_interval))
        agent_confirmed = False
        agent_identity: Optional[str] = None

        for _ in range(max_attempts):
            try:
                part_resp = await self.client.room.list_participants(
                    api.ListParticipantsRequest(room=room_name)
                )
                for p in part_resp.participants:
                    if self._is_agent_participant(p, agent_name):
                        agent_confirmed = True
                        agent_identity = p.identity
                        break
                if agent_confirmed:
                    break
            except Exception:
                pass
            await asyncio.sleep(poll_interval)

        if not agent_confirmed:
            try:
                await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=(
                    f"Agent dispatch handshake timed out: Worker '{agent_name}' did not join room '{room_name}' "
                    f"within {wait_timeout} seconds."
                ),
            )

        trainee_identity = f"trainee-{trainee_id}"
        token = self._build_trainee_token(
            room_name=room_name,
            identity=trainee_identity,
            name=trainee_name,
        )

        return UsvDoctorSessionResponse(
            room_name=room_info.name,
            room_sid=room_info.sid,
            livekit_url=settings.STS_LIVEKIT_URL,
            token=token,
            identity=trainee_identity,
            agent_status="ready",
            agent_identity=agent_identity,
            scenario=session_in.scenario or "doctor-detailing",
            language=session_in.language or "en-IN",
            patient_name=doctor_name,
        )

    async def list_sessions(self) -> List[RoomResponse]:
        if self.client is None:
            raise RuntimeError("LiveKitAPI client is required.")
        response = await self.client.room.list_rooms(api.ListRoomsRequest())
        sessions: List[RoomResponse] = []
        for room_info in response.rooms:
            if not room_info.name.startswith("USV-"):
                continue
            sessions.append(
                RoomResponse(
                    name=room_info.name,
                    sid=room_info.sid,
                    empty_timeout=room_info.empty_timeout,
                    max_participants=room_info.max_participants,
                    num_participants=room_info.num_participants,
                    metadata=room_info.metadata,
                    active_participants=[],
                )
            )
        return sessions

    async def get_session(self, room_name: str) -> Optional[RoomResponse]:
        if self.client is None:
            raise RuntimeError("LiveKitAPI client is required.")
        list_resp = await self.client.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
        if not list_resp.rooms:
            return None
        room_info = list_resp.rooms[0]
        part_resp = await self.client.room.list_participants(
            api.ListParticipantsRequest(room=room_name)
        )
        participants = [
            ParticipantInfo(
                identity=p.identity,
                name=p.name,
                state=str(p.state),
                joined_at=p.joined_at,
                metadata=p.metadata,
                attributes=dict(p.attributes) if hasattr(p, "attributes") else {},
            )
            for p in part_resp.participants
        ]
        return RoomResponse(
            name=room_info.name,
            sid=room_info.sid,
            empty_timeout=room_info.empty_timeout,
            max_participants=room_info.max_participants,
            num_participants=room_info.num_participants,
            metadata=room_info.metadata,
            active_participants=participants,
        )

    async def delete_session(self, room_name: str) -> bool:
        if self.client is None:
            raise RuntimeError("LiveKitAPI client is required.")
        try:
            await self.client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            return True
        except Exception as exc:
            logger.error(f"Error deleting USV room '{room_name}': {exc}")
            return False

    def generate_token(self, room_name: str, token_req: UsvDoctorTokenRequest) -> TokenResponse:
        jwt_token = self._build_trainee_token(
            room_name=room_name,
            identity=token_req.identity,
            name=token_req.name,
        )
        return TokenResponse(token=jwt_token, room_name=room_name, identity=token_req.identity)

    @staticmethod
    def _is_agent_participant(participant: api.ParticipantInfo, expected_agent_name: str) -> bool:
        if hasattr(participant, "kind"):
            if str(participant.kind).upper() in ("2", "AGENT", "PARTICIPANTINFO.KIND.AGENT"):
                return True
        ident = (participant.identity or "").lower()
        p_name = (participant.name or "").lower()
        expected = expected_agent_name.lower()
        return expected in ident or expected in p_name or ident.startswith("agent-") or ident.startswith("agent_")

    @staticmethod
    def _build_trainee_token(room_name: str, identity: str, name: Optional[str] = None) -> str:
        grants = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_sources=["microphone"],
        )
        token = (
            api.AccessToken(
                api_key=settings.STS_LIVEKIT_API_KEY,
                api_secret=settings.STS_LIVEKIT_API_SECRET,
            )
            .with_identity(identity)
            .with_grants(grants)
        )
        if name:
            token.with_name(name)
        return token.to_jwt()

    # ──────────────────────────────────────────────────────────
    #  Report Ingestion, Usage Metrics & QA Evaluation
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def aggregate_agent_usage(
        model_usage_raw: Optional[List[Dict[str, Any]]],
        fallback_model: Optional[str] = "gemini-3.8-live",
    ) -> Dict[str, Any]:
        """Aggregates token metrics and computes USD cost across LiveKit model_usage entries."""
        totals: Dict[str, Any] = {
            "input_tokens": 0,
            "input_cached_tokens": 0,
            "input_text_tokens": 0,
            "input_audio_tokens": 0,
            "output_tokens": 0,
            "output_text_tokens": 0,
            "output_audio_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        }
        if not isinstance(model_usage_raw, list):
            return totals

        for item in model_usage_raw:
            if not isinstance(item, dict):
                continue
            inp = _safe_int(
                item.get("input_tokens")
                or item.get("prompt_tokens")
                or item.get("llm_input_tokens")
            )
            in_cached = _safe_int(item.get("input_cached_tokens"))
            in_audio = _safe_int(
                item.get("input_audio_tokens") or item.get("llm_input_audio_tokens")
            )
            in_text = _safe_int(item.get("input_text_tokens"))
            if in_text == 0 and inp > in_audio:
                in_text = max(0, inp - in_audio)

            out = _safe_int(
                item.get("output_tokens")
                or item.get("completion_tokens")
                or item.get("llm_output_tokens")
            )
            out_audio = _safe_int(
                item.get("output_audio_tokens") or item.get("llm_output_audio_tokens")
            )
            out_reasoning = _safe_int(
                item.get("output_reasoning_tokens") or item.get("reasoning_tokens")
            )
            out_text = _safe_int(item.get("output_text_tokens"))
            if out_text == 0 and out > (out_audio + out_reasoning):
                out_text = max(0, out - out_audio - out_reasoning)

            item_total = _safe_int(item.get("total_tokens")) or (inp + out)

            totals["input_tokens"] += inp
            totals["input_cached_tokens"] += in_cached
            totals["input_text_tokens"] += in_text
            totals["input_audio_tokens"] += in_audio
            totals["output_tokens"] += out
            totals["output_text_tokens"] += out_text
            totals["output_audio_tokens"] += out_audio
            totals["reasoning_tokens"] += out_reasoning
            totals["total_tokens"] += item_total

        totals["cost_usd"] = compute_agent_usage_cost_usd(
            model_usage_raw, fallback_model=fallback_model
        )
        return totals

    @staticmethod
    def _normalize_chat_history_for_storage(
        raw_chat: Any,
        metadata: Dict[str, Any],
        custom_fields: Dict[str, Any],
    ) -> Optional[str]:
        if raw_chat is None:
            return json.dumps({"items": [], "metadata": metadata, "custom_fields": custom_fields})
        if isinstance(raw_chat, list):
            return json.dumps({"items": raw_chat, "metadata": metadata, "custom_fields": custom_fields})
        if isinstance(raw_chat, dict):
            payload = dict(raw_chat)
            if metadata and "metadata" not in payload:
                payload["metadata"] = metadata
            if custom_fields and "custom_fields" not in payload:
                payload["custom_fields"] = custom_fields
            return json.dumps(payload)
        return json.dumps({"items": [], "raw": str(raw_chat), "metadata": metadata})

    async def receive_report(self, payload: UsvDoctorWebhookPayload) -> Dict[str, Any]:
        if self.repository is None:
            raise RuntimeError("Repository is required for receiving reports.")

        meta = dict(payload.metadata or {})
        custom_fields = dict(payload.custom_fields or {})
        agent_info = payload.agent or {}

        duration_sec = (
            max(0, int(round(payload.duration_seconds)))
            if payload.duration_seconds is not None
            else _compute_duration_seconds(payload.started_at, payload.ended_at)
        )

        usage_totals = self.aggregate_agent_usage(
            payload.model_usage,
            fallback_model=meta.get("model_name") or "gemini-3.8-live",
        )
        agent_cost = float(usage_totals["cost_usd"])

        report_data = {
            "job_id": payload.job_id,
            "session_id": payload.session_id or payload.job_id,
            "room_name": payload.room_name or "unknown",
            "agent_name": agent_info.get("name") or "ira-voice-agent",
            "agent_role": agent_info.get("role") or "doctor",
            "started_at": payload.started_at,
            "ended_at": payload.ended_at,
            "duration_seconds": duration_sec,
            "termination_reason": payload.termination_reason or "normal",
            "error_info": json.dumps(payload.error) if payload.error else None,
            "status": "ongoing",
            "scenario": meta.get("scenario") or "doctor-detailing",
            "scenario_id": meta.get("scenario_id"),
            "title": meta.get("title"),
            "doctor_name": meta.get("doctor_name") or "AI Physician",
            "doctor_specialty": meta.get("doctor_specialty"),
            "clinic_setting": meta.get("clinic_setting"),
            "demeanor": meta.get("demeanor"),
            "trainee_name": meta.get("trainee_name") or "Medical Sales Representative",
            "trainee_id": meta.get("trainee_id") or "REP-101",
            "model_name": meta.get("model_name"),
            "language": meta.get("language"),
            "voice_id": meta.get("voice_id"),
            "session_metadata": json.dumps(meta) if meta else None,
            "chat_history": self._normalize_chat_history_for_storage(
                payload.chat_history, meta, custom_fields
            ),
            "events": json.dumps(payload.events) if payload.events is not None else None,
            "audio_recording_path": payload.audio_recording_path,
            "summary": None,
            "overall_score": 0,
            "readiness_assessment": None,
            "agent_model_usage": (
                json.dumps(payload.model_usage) if payload.model_usage is not None else None
            ),
            "agent_input_tokens": usage_totals["input_tokens"],
            "agent_input_cached_tokens": usage_totals["input_cached_tokens"],
            "agent_input_text_tokens": usage_totals["input_text_tokens"],
            "agent_input_audio_tokens": usage_totals["input_audio_tokens"],
            "agent_output_tokens": usage_totals["output_tokens"],
            "agent_output_text_tokens": usage_totals["output_text_tokens"],
            "agent_output_audio_tokens": usage_totals["output_audio_tokens"],
            "agent_reasoning_tokens": usage_totals["reasoning_tokens"],
            "agent_total_tokens": usage_totals["total_tokens"],
            "agent_cost_usd": agent_cost,
            "qa_cost_usd": 0.0,
            "total_cost_usd": agent_cost,
        }

        await self.repository.save_initial_report(report_data)
        return {
            "status": "success",
            "job_id": payload.job_id,
            "message": f"USV Doctor report for job {payload.job_id} received. Evaluation scheduled.",
        }

    async def evaluate_and_update(self, job_id: str) -> None:
        if self.repository is None:
            raise RuntimeError("Repository is required for evaluation.")

        row = await self.repository.get_by_job_id(job_id)
        if not row:
            logger.warning(f"USV Doctor evaluation skipped: job '{job_id}' not found.")
            return

        session_meta: Optional[Dict[str, Any]] = None
        if row.get("session_metadata"):
            try:
                session_meta = json.loads(row["session_metadata"])
            except Exception:
                session_meta = None

        agent_cost = float(row.get("agent_cost_usd") or 0.0)

        try:
            report_card, overall_score, qa_usage_info = await self.evaluation_service.evaluate_transcript(
                row.get("chat_history"),
                session_metadata=session_meta,
            )
            if report_card:
                usage_meta = qa_usage_info.get("usage_metadata") or {}
                qa_model = qa_usage_info.get("model_name")
                qa_prompt = _safe_int(usage_meta.get("promptTokenCount"))
                qa_cached = _safe_int(usage_meta.get("cachedContentTokenCount"))
                qa_cand = _safe_int(usage_meta.get("candidatesTokenCount"))
                qa_thoughts = _safe_int(usage_meta.get("thoughtsTokenCount"))
                qa_total = _safe_int(usage_meta.get("totalTokenCount")) or (
                    qa_prompt + qa_cand + qa_thoughts
                )
                qa_cost = (
                    compute_qa_cost_usd(
                        model_name=qa_model,
                        prompt_tokens=qa_prompt,
                        cached_tokens=qa_cached,
                        candidates_tokens=qa_cand,
                        thoughts_tokens=qa_thoughts,
                    )
                    if qa_total > 0 and qa_model
                    else 0.0
                )
                total_cost = round(agent_cost + qa_cost, 6)

                await self.repository.update_evaluation(
                    job_id=job_id,
                    summary=json.dumps(report_card),
                    overall_score=overall_score,
                    readiness_assessment=report_card.get("readiness_assessment", "Developing"),
                    status="completed",
                    qa_model_name=qa_model,
                    qa_usage_metadata=json.dumps(usage_meta) if usage_meta else None,
                    qa_prompt_tokens=qa_prompt,
                    qa_cached_tokens=qa_cached,
                    qa_candidates_tokens=qa_cand,
                    qa_thoughts_tokens=qa_thoughts,
                    qa_total_tokens=qa_total,
                    qa_cost_usd=qa_cost,
                    total_cost_usd=total_cost,
                )
            else:
                await self.repository.update_evaluation(
                    job_id=job_id,
                    summary=None,
                    overall_score=0,
                    readiness_assessment=None,
                    status="failed",
                    qa_cost_usd=0.0,
                    total_cost_usd=agent_cost,
                )
        except Exception as exc:
            logger.exception(f"USV Doctor evaluation error for job '{job_id}': {exc}")
            await self.repository.update_evaluation(
                job_id=job_id,
                summary=None,
                overall_score=0,
                readiness_assessment=None,
                status="failed",
                qa_cost_usd=0.0,
                total_cost_usd=agent_cost,
            )

    async def list_reports(self) -> UsvDoctorReportListResponse:
        if self.repository is None:
            raise RuntimeError("Repository is required.")
        rows = await self.repository.get_all()

        readiness_counts = {
            "Production Ready": 0,
            "Ready With Supervision": 0,
            "Developing": 0,
            "Needs Significant Coaching": 0,
            "Not Ready": 0,
        }
        summaries: List[UsvDoctorReportSummary] = []
        completed_scores: List[int] = []
        total_agent_tokens = 0
        total_qa_tokens = 0
        total_agent_cost = 0.0
        total_qa_cost = 0.0

        for r in rows:
            readiness = r.get("readiness_assessment") or "Developing"
            agent_tok = _safe_int(r.get("agent_total_tokens"))
            qa_tok = _safe_int(r.get("qa_total_tokens"))
            a_cost = float(r.get("agent_cost_usd") or 0.0)
            q_cost = float(r.get("qa_cost_usd") or 0.0)
            t_cost = float(r.get("total_cost_usd") if r.get("total_cost_usd") is not None else (a_cost + q_cost))

            total_agent_tokens += agent_tok
            total_qa_tokens += qa_tok
            total_agent_cost += a_cost
            total_qa_cost += q_cost

            summaries.append(
                UsvDoctorReportSummary(
                    job_id=r["job_id"],
                    room=r.get("room_name"),
                    started_at=r.get("started_at"),
                    ended_at=r.get("ended_at"),
                    duration_seconds=r.get("duration_seconds"),
                    overall_score=r.get("overall_score"),
                    status=r.get("status"),
                    customer_name=r.get("doctor_name"),
                    sales_rep=r.get("trainee_name"),
                    agent_type=r.get("agent_name"),
                    scenario=r.get("scenario"),
                    doctor_specialty=r.get("doctor_specialty"),
                    readiness_assessment=readiness,
                    agent_total_tokens=agent_tok,
                    qa_total_tokens=qa_tok,
                    agent_cost_usd=round(a_cost, 6),
                    qa_cost_usd=round(q_cost, 6),
                    total_cost_usd=round(t_cost, 6),
                )
            )
            if r.get("status") == "completed":
                completed_scores.append(_safe_int(r.get("overall_score")))
                if readiness in readiness_counts:
                    readiness_counts[readiness] += 1

        total_calls = len(completed_scores)
        avg_score = int(sum(completed_scores) / total_calls) if total_calls else 0

        return UsvDoctorReportListResponse(
            reports=summaries,
            stats={
                "total_calls": total_calls,
                "avg_score": avg_score,
                "readiness": readiness_counts,
                "total_agent_tokens": total_agent_tokens,
                "total_qa_tokens": total_qa_tokens,
                "total_agent_cost_usd": round(total_agent_cost, 6),
                "total_qa_cost_usd": round(total_qa_cost, 6),
                "total_cost_usd": round(total_agent_cost + total_qa_cost, 6),
            },
        )

    async def get_report(self, job_id: str) -> Optional[UsvDoctorReportDetail]:
        if self.repository is None:
            raise RuntimeError("Repository is required.")
        r = await self.repository.get_by_job_id(job_id)
        if not r:
            return None

        summary = r.get("summary")
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                pass

        events = r.get("events")
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except Exception:
                pass

        agent_raw = None
        if r.get("agent_model_usage"):
            try:
                agent_raw = json.loads(r["agent_model_usage"])
            except Exception:
                agent_raw = None

        qa_raw = None
        if r.get("qa_usage_metadata"):
            try:
                qa_raw = json.loads(r["qa_usage_metadata"])
            except Exception:
                qa_raw = None

        parsed_chat = self._parse_chat_for_frontend(r.get("chat_history"))
        a_cost = float(r.get("agent_cost_usd") or 0.0)
        q_cost = float(r.get("qa_cost_usd") or 0.0)
        t_cost = float(r.get("total_cost_usd") if r.get("total_cost_usd") is not None else (a_cost + q_cost))

        return UsvDoctorReportDetail(
            job_id=r["job_id"],
            session_id=r.get("session_id"),
            room_id=r.get("session_id"),
            room=r.get("room_name"),
            started_at=r.get("started_at"),
            ended_at=r.get("ended_at"),
            duration_seconds=r.get("duration_seconds"),
            termination_reason=r.get("termination_reason"),
            summary=summary,
            overall_score=r.get("overall_score"),
            status=r.get("status"),
            customer_name=r.get("doctor_name"),
            agent_type=r.get("agent_name"),
            sales_rep=r.get("trainee_name"),
            trainee_id=r.get("trainee_id"),
            scenario=r.get("scenario"),
            title=r.get("title"),
            doctor_specialty=r.get("doctor_specialty"),
            clinic_setting=r.get("clinic_setting"),
            demeanor=r.get("demeanor"),
            model_name=r.get("model_name"),
            language=r.get("language"),
            voice_id=r.get("voice_id"),
            chat_history=parsed_chat,
            events=events,
            agent_usage=AgentUsageSummary(
                input_tokens=_safe_int(r.get("agent_input_tokens")),
                input_cached_tokens=_safe_int(r.get("agent_input_cached_tokens")),
                input_text_tokens=_safe_int(r.get("agent_input_text_tokens")),
                input_audio_tokens=_safe_int(r.get("agent_input_audio_tokens")),
                output_tokens=_safe_int(r.get("agent_output_tokens")),
                output_text_tokens=_safe_int(r.get("agent_output_text_tokens")),
                output_audio_tokens=_safe_int(r.get("agent_output_audio_tokens")),
                reasoning_tokens=_safe_int(r.get("agent_reasoning_tokens")),
                total_tokens=_safe_int(r.get("agent_total_tokens")),
                cost_usd=round(a_cost, 6),
                raw=agent_raw,
            ),
            qa_usage=QAUsageSummary(
                model_name=r.get("qa_model_name"),
                prompt_tokens=_safe_int(r.get("qa_prompt_tokens")),
                cached_tokens=_safe_int(r.get("qa_cached_tokens")),
                candidates_tokens=_safe_int(r.get("qa_candidates_tokens")),
                thoughts_tokens=_safe_int(r.get("qa_thoughts_tokens")),
                total_tokens=_safe_int(r.get("qa_total_tokens")),
                cost_usd=round(q_cost, 6),
                raw=qa_raw,
            ),
            total_cost_usd=round(t_cost, 6),
            created_at=r.get("created_at"),
        )

    async def get_report_status(self, job_id: str) -> Optional[Dict[str, str]]:
        if self.repository is None:
            raise RuntimeError("Repository is required.")
        row = await self.repository.get_by_job_id(job_id)
        if not row:
            return None
        return {"status": row.get("status") or "ongoing"}

    async def retry_evaluation(self, job_id: str) -> Optional[Dict[str, Any]]:
        if self.repository is None:
            raise RuntimeError("Repository is required.")
        return await self.repository.reset_for_retry(job_id)

    @staticmethod
    def _parse_chat_for_frontend(chat_history_raw: Any) -> List[Dict[str, Any]]:
        if not chat_history_raw:
            return []
        data = chat_history_raw
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                return []
        items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        parsed: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if "type" in item and item.get("type") not in ("message", "text", "transcript"):
                continue
            role = (item.get("role") or "").strip().lower()
            if role in ("system", "tool"):
                continue
            content = item.get("content", "")
            text = ""
            if isinstance(content, list):
                text = " ".join(str(part) for part in content if isinstance(part, str)).strip()
            elif isinstance(content, str):
                text = content.strip()
            if not text:
                for key in ("text", "message", "transcript"):
                    val = item.get(key)
                    if isinstance(val, str) and val.strip():
                        text = val.strip()
                        break
            if not text:
                continue
            normalized_role = "user" if role in ("user", "trainee", "human") else "assistant"
            parsed.append(
                {
                    "role": normalized_role,
                    "text": text,
                    "interrupted": bool(item.get("interrupted", False)),
                }
            )
        return parsed
