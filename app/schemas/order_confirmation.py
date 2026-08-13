from pydantic import BaseModel, Field
from typing import Optional

class OrderConfirmationDialRequest(BaseModel):
    """
    Request payload to trigger an automated outbound order confirmation call.
    Carries full order metadata required by the naaptol-order-confirmation voice agent.
    """
    phone_number: str = Field(
        ...,
        description="Customer destination phone number in E.164 format (e.g. +919876543210)"
    )
    customer_name: str = Field(
        "Customer",
        description="Name of the customer"
    )
    order_id: str = Field(
        ...,
        description="Unique order ID (e.g. ORD-987654)"
    )
    product_name: str = Field(
        ...,
        description="Name of the product ordered"
    )
    product_price: float = Field(
        ...,
        description="Base price of the product"
    )
    shipping_price: float = Field(
        0.0,
        description="Shipping charge applied (if 0, agent offers no waiver; if > 0, agent can waive upon cancellation intent)"
    )
    total_order_amount: float = Field(
        ...,
        description="Total order payable amount (product_price + shipping_price)"
    )
    expected_delivery_date: str = Field(
        "3 to 5 business days",
        description="Expected delivery date or timeframe string"
    )
    language: str = Field(
        "hindi",
        description="Language code for the conversation ('hindi', 'english', 'malayalam', 'tamil')"
    )
    outbound_trunk_id: Optional[str] = Field(
        None,
        description="Optional stored outbound SIP trunk ID. Defaults to inline Twilio SIP trunk config if omitted."
    )


class OrderConfirmationDialResponse(BaseModel):
    """
    Response model returned after dispatching the agent and dialing the phone call.
    """
    room_name: str = Field(..., description="LiveKit room name where the call session was initiated")
    participant_identity: str = Field(..., description="SIP participant identity assigned to the phone caller")
    call_status: str = Field(..., description="Initial SIP call status ('dialing')")
    agent_name: str = Field("naaptol-order-confirmation", description="Dispatched LiveKit agent name")
    order_id: str = Field(..., description="Order ID being confirmed")
    customer_name: str = Field(..., description="Customer name being called")
    message: str = Field("Outbound order confirmation call initiated successfully")
