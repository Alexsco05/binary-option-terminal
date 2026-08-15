# ================================================================
# GIDEON — memory/knowledge.py
# ----------------------------------------------------------------
# Per-device in-memory knowledge graph: nodes extracted from
# conversation or research, deduplicated by normalized label, with
# undirected relationship links. Moved from server.py with zero
# behavior change.
# ================================================================

import re
import threading

KNOWLEDGE_STORE  = {}  # device_id -> {node_id: {label, category, related_to}}
_KNOWLEDGE_GUARD = threading.Lock()


def _normalize_label(label: str) -> str:
    return re.sub(r'[^a-z0-9\s]', '', label.lower()).strip()


def _get_knowledge(device_id: str) -> dict:
    return KNOWLEDGE_STORE.setdefault(device_id, {})


def merge_nodes(device_id: str, extracted_nodes: list) -> dict:
    """
    Folds freshly extracted nodes into this device's running knowledge
    graph. Duplicate detection is a simple normalized-label match —
    good enough to prove out linking and search before anything
    fancier (embeddings) is worth building. related_to links are
    treated as undirected: if A relates to B, B relates to A.
    """
    store = _get_knowledge(device_id)

    with _KNOWLEDGE_GUARD:
        label_to_id = {n["label_norm"]: nid for nid, n in store.items()}
        local_to_global = {}  # this batch's node ids -> store-wide ids

        for n in extracted_nodes:
            label = str(n.get("label", "")).strip()
            if not label:
                continue
            norm = _normalize_label(label)
            if norm in label_to_id:
                global_id = label_to_id[norm]
            else:
                global_id = f"k{len(store) + 1}"
                store[global_id] = {
                    "label":       label,
                    "label_norm":  norm,
                    "category":    str(n.get("category", "")).strip() or "idea",
                    "related_to":  set(),
                }
                label_to_id[norm] = global_id
            local_to_global[n.get("id")] = global_id

        for n in extracted_nodes:
            src = local_to_global.get(n.get("id"))
            if not src:
                continue
            for rel in (n.get("related_to") or []):
                dst = local_to_global.get(rel)
                if dst and dst != src:
                    store[src]["related_to"].add(dst)
                    store[dst]["related_to"].add(src)

    return store
