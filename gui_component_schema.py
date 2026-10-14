from __future__ import annotations

ALLOWED_STATUS = {
    "DESIGN_CANDIDATE",
    "IMPLEMENTATION_READY",
    "RUNTIME_CANDIDATE",
    "COMPONENT_CURRENT",
}

ALLOWED_BINDING = {
    "PARAM_CONTINUOUS",
    "PARAM_BIPOLAR",
    "PARAM_STEPPED",
    "PARAM_ENUM",
    "PARAM_BOOL",
    "PARAM_TEXT",
    "TELEMETRY_SCALAR",
    "TELEMETRY_VECTOR",
    "TELEMETRY_HISTORY",
    "TELEMETRY_AUDIO_DERIVED",
    "STATE_ACTION",
    "STATE_SELECTOR",
    "STATIC_PRESENTATION",
}

ALLOWED_RENDERING = {
    "VECTOR_STATIC",
    "VECTOR_DYNAMIC",
    "RASTER_ASSET",
    "FILMSTRIP_ASSET",
    "RUNTIME_DRAWN",
    "TEXT_RUNTIME",
    "TELEMETRY_RENDERED",
}

ALLOWED_UPDATE = {
    "STATIC",
    "EVENT_DRIVEN",
    "PARAMETER_DRIVEN",
    "UI_ANIMATION",
    "METER_TELEMETRY",
    "ANALYSIS_TELEMETRY",
}

REQUIRED_FIELDS = {
    "component_id",
    "semantic_name",
    "family",
    "status",
    "size_classes",
    "supported_roles",
    "binding_class",
    "interaction_states",
    "rendering_layers",
    "logical_bounds",
    "resize_policy",
    "motion_update_class",
    "assets",
    "runtime_adapter",
    "qa_fixtures",
    "known_limits",
}


class GuiComponentSchemaError(ValueError):
    pass


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise GuiComponentSchemaError(message)


def validate_component_contract(payload: dict) -> dict:
    _need(isinstance(payload, dict), "COMPONENT_NOT_OBJECT")
    missing = sorted(REQUIRED_FIELDS - set(payload))
    _need(not missing, "MISSING_FIELDS:" + ",".join(missing))

    _need(isinstance(payload["component_id"], str) and payload["component_id"].strip(), "COMPONENT_ID_INVALID")
    _need(isinstance(payload["semantic_name"], str) and payload["semantic_name"].strip(), "SEMANTIC_NAME_INVALID")
    _need(isinstance(payload["family"], str) and payload["family"].strip(), "FAMILY_INVALID")
    _need(payload["status"] in ALLOWED_STATUS, "STATUS_INVALID")

    sizes = payload["size_classes"]
    _need(isinstance(sizes, list) and sizes and all(isinstance(x, str) and x for x in sizes), "SIZE_CLASSES_INVALID")

    roles = payload["supported_roles"]
    _need(isinstance(roles, list) and roles and all(isinstance(x, str) and x for x in roles), "SUPPORTED_ROLES_INVALID")

    bindings = payload["binding_class"]
    if isinstance(bindings, str):
        bindings = [bindings]
    _need(isinstance(bindings, list) and bindings, "BINDING_CLASS_INVALID")
    _need(set(bindings).issubset(ALLOWED_BINDING), "BINDING_CLASS_UNSUPPORTED")

    states = payload["interaction_states"]
    _need(isinstance(states, list) and states and all(isinstance(x, str) and x for x in states), "INTERACTION_STATES_INVALID")

    layers = payload["rendering_layers"]
    _need(isinstance(layers, list) and layers, "RENDERING_LAYERS_INVALID")
    for layer in layers:
        _need(isinstance(layer, dict), "RENDERING_LAYER_INVALID")
        _need(layer.get("class") in ALLOWED_RENDERING, "RENDERING_CLASS_UNSUPPORTED")

    bounds = payload["logical_bounds"]
    _need(isinstance(bounds, dict), "LOGICAL_BOUNDS_INVALID")
    for key in ("width", "height"):
        _need(isinstance(bounds.get(key), (int, float)) and bounds[key] > 0, f"LOGICAL_BOUNDS_{key.upper()}_INVALID")

    _need(isinstance(payload["resize_policy"], str) and payload["resize_policy"], "RESIZE_POLICY_INVALID")

    updates = payload["motion_update_class"]
    if isinstance(updates, str):
        updates = [updates]
    _need(isinstance(updates, list) and updates, "MOTION_UPDATE_CLASS_INVALID")
    _need(set(updates).issubset(ALLOWED_UPDATE), "MOTION_UPDATE_CLASS_UNSUPPORTED")

    _need(isinstance(payload["assets"], list), "ASSETS_INVALID")
    _need(isinstance(payload["runtime_adapter"], str) and payload["runtime_adapter"].strip(), "RUNTIME_ADAPTER_INVALID")
    _need(isinstance(payload["qa_fixtures"], list) and payload["qa_fixtures"], "QA_FIXTURES_INVALID")
    _need(isinstance(payload["known_limits"], list), "KNOWN_LIMITS_INVALID")

    return {
        "status": "PASS",
        "component_id": payload["component_id"],
        "binding_classes": bindings,
        "rendering_classes": [x["class"] for x in layers],
        "update_classes": updates,
    }
