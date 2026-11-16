"""
Pydantic schemas for Stage 1C Voice Rating Parameters evaluation phase (IRA AI SOP).
Evaluates 27 granular parameters across 5 sessions:
- Block A: Opening (A1 to A4)
- Block B: Initial Addressal (B1 to B2)
- Block C: Persuasion (C1 to C5)
- Block D: Closure (D1 to D4)
- Block E: Overall Communication (E1 to E12)
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class VoiceVerdict(str, Enum):
    FOLLOWED = "followed"
    PARTIALLY_FOLLOWED = "partially followed"
    NOT_FOLLOWED = "not followed"
    NOT_POSSIBLE = "not possible to analyze"


class VoiceRatingParameterItem(BaseModel):
    code: str = Field(description="Parameter code e.g. A1, B2, C1, D3, E2")
    parameter_question: str = Field(description="Evaluation question from SOP CSV")
    verdict: VoiceVerdict = Field(description="Adherence verdict: followed, partially followed, not followed, or not possible to analyze")
    evidence_quote: str = Field(default="", description="Verbatim quote from dialogue if applicable")
    reasoning: str = Field(default="", description="Detailed clinical and behavioral justification for the verdict")


# --- Raw Sub-call Schemas for Gemini Structured JSON Generation ---

class Stage1CBlocksABCDRawResponse(BaseModel):
    """Raw LLM output schema for Sub-call 1: Structural Blocks A, B, C, D (15 parameters)."""
    session_a_parameters: List[VoiceRatingParameterItem] = Field(description="Audit of Opening parameters A1 through A4")
    session_b_parameters: List[VoiceRatingParameterItem] = Field(description="Audit of Initial Addressal parameters B1 and B2")
    session_c_parameters: List[VoiceRatingParameterItem] = Field(description="Audit of Persuasion parameters C1 through C5")
    session_d_parameters: List[VoiceRatingParameterItem] = Field(description="Audit of Closure parameters D1 through D4")


class Stage1CBlockERawResponse(BaseModel):
    """Raw LLM output schema for Sub-call 2: Holistic Communication Block E (Parameters E1, E3-E12)."""
    session_e_parameters: List[VoiceRatingParameterItem] = Field(description="Audit of Communication parameters E1, E3 through E12")


# --- Consolidated Application & API Schemas ---

class VoiceRatingSessionBlock(BaseModel):
    session_id: str = Field(description="'A', 'B', 'C', 'D', 'E'")
    session_title: str = Field(description="'Opening', 'Initial Addressal', 'Persuasion', 'Closure', 'Overall Communication'")
    parameters: List[VoiceRatingParameterItem] = Field(default_factory=list)
    followed_count: int = 0
    partially_followed_count: int = 0
    not_followed_count: int = 0
    not_possible_count: int = 0
    adherence_percentage: float = 0.0

    @classmethod
    def from_parameters(
        cls,
        session_id: str,
        session_title: str,
        parameters: List[VoiceRatingParameterItem],
    ) -> "VoiceRatingSessionBlock":
        followed = sum(1 for p in parameters if p.verdict == VoiceVerdict.FOLLOWED)
        partially = sum(1 for p in parameters if p.verdict == VoiceVerdict.PARTIALLY_FOLLOWED)
        not_followed = sum(1 for p in parameters if p.verdict == VoiceVerdict.NOT_FOLLOWED)
        not_possible = sum(1 for p in parameters if p.verdict == VoiceVerdict.NOT_POSSIBLE)

        analyzable_count = len(parameters) - not_possible
        if analyzable_count > 0:
            pct = round((followed / analyzable_count) * 100.0, 1)
        else:
            pct = 0.0

        return cls(
            session_id=session_id,
            session_title=session_title,
            parameters=parameters,
            followed_count=followed,
            partially_followed_count=partially,
            not_followed_count=not_followed,
            not_possible_count=not_possible,
            adherence_percentage=pct,
        )


class VoiceRatingAuditResponse(BaseModel):
    session_a_opening: VoiceRatingSessionBlock
    session_b_initial_addressal: VoiceRatingSessionBlock
    session_c_persuasion: VoiceRatingSessionBlock
    session_d_closure: VoiceRatingSessionBlock
    session_e_overall_comm: VoiceRatingSessionBlock
    total_parameters_evaluated: int = 27
    overall_voice_adherence_pct: float = 0.0

    @classmethod
    def from_blocks(
        cls,
        block_a: VoiceRatingSessionBlock,
        block_b: VoiceRatingSessionBlock,
        block_c: VoiceRatingSessionBlock,
        block_d: VoiceRatingSessionBlock,
        block_e: VoiceRatingSessionBlock,
    ) -> "VoiceRatingAuditResponse":
        all_blocks = [block_a, block_b, block_c, block_d, block_e]
        all_params = [p for b in all_blocks for p in b.parameters]

        total_analyzable = sum(1 for p in all_params if p.verdict != VoiceVerdict.NOT_POSSIBLE)
        total_followed = sum(1 for p in all_params if p.verdict == VoiceVerdict.FOLLOWED)

        if total_analyzable > 0:
            overall_pct = round((total_followed / total_analyzable) * 100.0, 1)
        else:
            overall_pct = 0.0

        return cls(
            session_a_opening=block_a,
            session_b_initial_addressal=block_b,
            session_c_persuasion=block_c,
            session_d_closure=block_d,
            session_e_overall_comm=block_e,
            total_parameters_evaluated=len(all_params),
            overall_voice_adherence_pct=overall_pct,
        )
