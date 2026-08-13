"""Local Ollama adapter for one provider-independent structured decision."""

import json
from copy import deepcopy
from http.client import HTTPConnection, HTTPException
from typing import Annotated, Any, Protocol, Self, cast
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)

from travelops_recovery_agent.agent.decision_model import (
    DecisionModelError,
    ModelErrorCode,
    ModelRequest,
)
from travelops_recovery_agent.agent.models import (
    AGENT_DECISION_ADAPTER,
    AgentContractModel,
    AgentDecision,
    ConversationRole,
    ReferenceText,
)

MAX_RESPONSE_BYTES = 1_000_000


class OllamaConfig(AgentContractModel):
    """Credential-free settings for the local Ollama REST endpoint."""

    base_url: str = "http://127.0.0.1:11434"
    model: ReferenceText
    timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 60.0

    @model_validator(mode="after")
    def require_local_http_origin(self) -> Self:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "http":
            raise ValueError("Ollama base_url must use local HTTP")
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama base_url must use a loopback host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Ollama base_url must not contain credentials")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("Ollama base_url must be an origin without a path")
        if parsed.port is None:
            raise ValueError("Ollama base_url must include an explicit port")
        return self

    @property
    def chat_url(self) -> str:
        """Return the one provider endpoint used by this adapter."""

        return f"{self.base_url.rstrip('/')}/api/chat"


class OllamaTransport(Protocol):
    """Injectable JSON transport keeping adapter tests offline."""

    def post_json(
        self,
        url: str,
        payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> object:
        """POST JSON and return decoded provider data."""


class OllamaTransportError(Exception):
    """Safe transport failure without response bodies or connection details."""


class StandardLibraryOllamaTransport:
    """Small synchronous local HTTP transport with a bounded response body."""

    def post_json(
        self,
        url: str,
        payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> object:
        """Call local Ollama without adding a provider SDK dependency."""

        parsed = urlsplit(url)
        if parsed.hostname is None or parsed.port is None:
            raise OllamaTransportError("local Ollama endpoint is invalid")
        connection = HTTPConnection(
            parsed.hostname,
            parsed.port,
            timeout=timeout_seconds,
        )
        body = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            connection.request(
                "POST",
                parsed.path,
                body=body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
            if not 200 <= response.status < 300:
                raise OllamaTransportError("local Ollama request failed")
            if len(response_body) > MAX_RESPONSE_BYTES:
                raise OllamaTransportError("local Ollama response was too large")
            decoded: object = json.loads(response_body.decode("utf-8"))
            return decoded
        except OllamaTransportError:
            raise
        except (
            HTTPException,
            OSError,
            TimeoutError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            raise OllamaTransportError("local Ollama request failed") from None
        finally:
            connection.close()


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    role: str
    content: str


class _OllamaChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    message: _OllamaMessage
    done: bool


class OllamaDecisionModel:
    """Translate Ollama chat responses to application-owned decisions."""

    def __init__(
        self,
        config: OllamaConfig,
        *,
        transport: OllamaTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport or StandardLibraryOllamaTransport()

    def decide(self, request: ModelRequest) -> AgentDecision:
        """Request and validate exactly one structured agent decision."""

        payload = self._build_payload(request)
        try:
            raw_response = self._transport.post_json(
                self._config.chat_url,
                payload,
                self._config.timeout_seconds,
            )
        except Exception:
            raise DecisionModelError(
                ModelErrorCode.INVOCATION_FAILED,
                "local model invocation failed",
            ) from None

        try:
            response = _OllamaChatResponse.model_validate(raw_response)
            if not response.done or response.message.role != "assistant":
                raise ValueError("incomplete Ollama response")
            return AGENT_DECISION_ADAPTER.validate_json(response.message.content)
        except (ValidationError, ValueError):
            raise DecisionModelError(
                ModelErrorCode.MALFORMED_OUTPUT,
                "local model output did not match the decision schema",
            ) from None

    def _build_payload(self, request: ModelRequest) -> dict[str, JsonValue]:
        decision_schema = self._build_decision_schema(request)
        tool_payload = [tool.model_dump(mode="json") for tool in request.tools]
        messages: list[JsonValue] = [
            {
                "role": "system",
                "content": self._system_instruction(decision_schema, tool_payload),
            }
        ]
        role_mapping = {
            ConversationRole.OPERATOR: "user",
            ConversationRole.AGENT: "assistant",
            ConversationRole.TOOL: "user",
            ConversationRole.APPLICATION: "system",
        }
        messages.extend(
            {
                "role": role_mapping[message.role],
                "content": message.content,
            }
            for message in request.messages
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Safe structured observations for this turn:\n"
                    + json.dumps(
                        [
                            observation.model_dump(mode="json")
                            for observation in request.observations
                        ],
                        allow_nan=False,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\nReturn exactly one next decision."
                ),
            }
        )
        return {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": decision_schema,
            "options": {"temperature": 0},
        }

    @staticmethod
    def _build_decision_schema(request: ModelRequest) -> dict[str, JsonValue]:
        """Bind each call-tool schema branch to one exact Phase 4 input schema."""

        schema = deepcopy(AGENT_DECISION_ADAPTER.json_schema())
        definitions = cast(dict[str, dict[str, Any]], schema["$defs"])
        call_template = definitions.pop("CallToolDecision")
        definitions.pop("JsonValue", None)

        call_references: list[dict[str, str]] = []
        for tool in request.tools:
            definition_name = f"CallToolDecision_{tool.name}"
            call_definition = deepcopy(call_template)
            properties = cast(
                dict[str, Any],
                call_definition["properties"],
            )
            properties["tool_name"] = {
                "const": tool.name,
                "type": "string",
            }
            properties["arguments"] = OllamaDecisionModel._hoist_tool_definitions(
                tool.name,
                tool.input_schema,
                definitions,
            )
            call_definition["title"] = definition_name
            definitions[definition_name] = call_definition
            call_references.append({"$ref": f"#/$defs/{definition_name}"})

        schema.pop("discriminator", None)
        schema["oneOf"] = [
            *call_references,
            {"$ref": "#/$defs/AskInformationDecision"},
            {"$ref": "#/$defs/FinishDecision"},
        ]
        return cast(dict[str, JsonValue], schema)

    @staticmethod
    def _hoist_tool_definitions(
        tool_name: str,
        input_schema: dict[str, JsonValue],
        root_definitions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Move nested tool definitions where Ollama's converter resolves refs."""

        schema = cast(dict[str, Any], deepcopy(input_schema))
        nested_definitions = cast(
            dict[str, dict[str, Any]],
            schema.pop("$defs", {}),
        )
        reference_mapping = {
            f"#/$defs/{name}": f"#/$defs/ToolInput_{tool_name}_{name}"
            for name in nested_definitions
        }

        def rewrite_references(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: (
                        reference_mapping.get(item, item)
                        if key == "$ref" and isinstance(item, str)
                        else rewrite_references(item)
                    )
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [rewrite_references(item) for item in value]
            return value

        for name, definition in nested_definitions.items():
            root_name = f"ToolInput_{tool_name}_{name}"
            root_definitions[root_name] = cast(
                dict[str, Any], rewrite_references(definition)
            )
        return cast(dict[str, Any], rewrite_references(schema))

    @staticmethod
    def _system_instruction(
        decision_schema: dict[str, JsonValue],
        tools: list[dict[str, JsonValue]],
    ) -> str:
        return (
            "You select the next step in a bounded, read-only airline recovery "
            "investigation. Return exactly one JSON decision matching the schema. "
            "Do not invent tools, evidence, availability, prices, or ticket rules. "
            "For a tool call, arguments must be exactly the object described by that "
            "tool's input_schema: do not wrap it or add fields. Use concise summaries "
            "and never include hidden reasoning.\n"
            "Available read-only tools:\n"
            + json.dumps(
                tools,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\nDecision JSON schema:\n"
            + json.dumps(
                decision_schema,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
