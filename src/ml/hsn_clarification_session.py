"""
Module: src/ml/hsn_clarification_session.py
Description: Persistent HSN Clarification Session Manager adhering to Data Contract Schema v1.0.0.

Manages the lifecycle of customer clarification sessions:
IN_PROGRESS -> SUBMITTED -> ENRICHMENT_IN_PROGRESS -> RECLASSIFICATION_IN_PROGRESS -> COMPLETED (or MANUAL_REVIEW / FAILED).
Ensures crash-resilient SQLite persistence, deduplication, and transition auditing.
"""

import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("gst_sentinel.clarification_session")
logger.setLevel(logging.INFO)

SCHEMA_VERSION = "1.0.0"

ALLOWED_STATUSES = {
    "IN_PROGRESS",
    "SUBMITTED",
    "VERIFICATION_IN_PROGRESS",
    "ENRICHMENT_PENDING",
    "ENRICHMENT_IN_PROGRESS",
    "ENRICHMENT_COMPLETED",
    "ENRICHMENT_FAILED",
    "RECLASSIFICATION_IN_PROGRESS",
    "RECLASSIFICATION_COMPLETED",
    "COMPLETED",
    "MANUAL_REVIEW",
    "FAILED",
}

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "hsn_clarification_sessions.db"


def utc_now_iso() -> str:
    """Returns current ISO 8601 UTC timestamp ending in Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_product_key(text: str) -> str:
    """Normalizes product description for robust de-duplication."""
    t = (text or "").lower().strip()
    t = re.sub(r"\b\d+\s*(pcs|pieces|nos|numbers|qty|kg|kgs|g|gms|lot|meters?|mtrs?)\b", " ", t)
    t = re.sub(r"[^\w\s\/\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


class ClarificationSession:
    """Represents an HSN Clarification Session adhering to Data Contract Schema v1.0.0."""

    def __init__(
        self,
        session_id: str,
        product_description: str,
        ambiguity_analysis: Dict[str, Any],
        generated_questions: List[Dict[str, Any]],
        customer_answers: Optional[List[Dict[str, Any]]] = None,
        status: str = "IN_PROGRESS",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        submitted_at: Optional[str] = None,
        status_history: Optional[List[Dict[str, Any]]] = None,
        verification_result: Optional[Dict[str, Any]] = None,
        schema_version: str = SCHEMA_VERSION,
        enriched_description: Optional[str] = None,
        enrichment_status: Optional[str] = None,
        enrichment_prompt_version: Optional[str] = None,
        enrichment_timestamp: Optional[str] = None,
        validation_result: Optional[Dict[str, Any]] = None,
        reclassification_status: Optional[str] = None,
    ):
        self.session_id = str(session_id)
        self.schema_version = str(schema_version or SCHEMA_VERSION)
        self.product_description = str(product_description).strip()
        self.ambiguity_analysis = ambiguity_analysis or {}
        self.generated_questions = generated_questions or []
        self.customer_answers = customer_answers or []
        self.status = str(status).upper()
        now = utc_now_iso()
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.submitted_at = submitted_at
        self.status_history = status_history or [
            {"from_status": None, "to_status": self.status, "timestamp": self.created_at, "reason": "Session created"}
        ]
        self.verification_result = verification_result
        self.enriched_description = enriched_description
        self.enrichment_status = enrichment_status
        self.enrichment_prompt_version = enrichment_prompt_version
        self.enrichment_timestamp = enrichment_timestamp
        self.validation_result = validation_result
        self.reclassification_status = reclassification_status

    def to_contract_dict(self) -> Dict[str, Any]:
        """
        Returns exact dictionary adhering strictly to
        HSN Clarification Session Data Contract Schema v1.0.0.
        """
        res = {
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "product_description": self.product_description,
            "ambiguity_analysis": self.ambiguity_analysis,
            "generated_questions": self.generated_questions,
            "customer_answers": self.customer_answers,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "submitted_at": self.submitted_at,
        }
        if self.enriched_description:
            res["enriched_description"] = self.enriched_description
        if self.enrichment_status:
            res["enrichment_status"] = self.enrichment_status
        if self.validation_result:
            res["validation_result"] = self.validation_result
        if self.reclassification_status:
            res["reclassification_status"] = self.reclassification_status
        return res

    def to_detail_dict(self) -> Dict[str, Any]:
        """Includes full audit history, verification result, and enrichment fields."""
        d = self.to_contract_dict()
        d["status_history"] = self.status_history
        d["verification_result"] = self.verification_result
        d["enriched_description"] = self.enriched_description
        d["enrichment_status"] = self.enrichment_status
        d["enrichment_prompt_version"] = self.enrichment_prompt_version
        d["enrichment_timestamp"] = self.enrichment_timestamp
        d["validation_result"] = self.validation_result
        d["reclassification_status"] = self.reclassification_status
        return d


class ClarificationSessionManager:
    """
    Thread-safe, crash-resilient manager for HSN Clarification Sessions.
    Persists sessions in SQLite and enforces lifecycle status transitions.
    """

    _instance: Optional["ClarificationSessionManager"] = None

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clarification_sessions (
                    session_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    product_description TEXT NOT NULL,
                    normalized_key TEXT NOT NULL,
                    ambiguity_analysis TEXT NOT NULL,
                    generated_questions TEXT NOT NULL,
                    customer_answers TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    submitted_at TEXT,
                    status_history TEXT NOT NULL,
                    verification_result TEXT,
                    enriched_description TEXT,
                    enrichment_status TEXT,
                    enrichment_prompt_version TEXT,
                    enrichment_timestamp TEXT,
                    validation_result TEXT,
                    reclassification_status TEXT
                );
                """
            )
            # Add columns if migrating from earlier schema
            for col, col_type in [
                ("enriched_description", "TEXT"),
                ("enrichment_status", "TEXT"),
                ("enrichment_prompt_version", "TEXT"),
                ("enrichment_timestamp", "TEXT"),
                ("validation_result", "TEXT"),
                ("reclassification_status", "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE clarification_sessions ADD COLUMN {col} {col_type};")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_key_status ON clarification_sessions(normalized_key, status);"
            )
            conn.commit()

    def create_or_get_active_session(
        self,
        product_description: str,
        ambiguity_analysis: Optional[Dict[str, Any]] = None,
        generated_questions: Optional[List[Dict[str, Any]]] = None,
        retrieved_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> ClarificationSession:
        """
        Creates a new session or returns an existing IN_PROGRESS session for the same product
        to prevent duplicate sessions from being created unintentionally.
        """
        p_desc = str(product_description or "").strip()
        norm_key = normalize_product_key(p_desc)

        # Check for existing IN_PROGRESS session
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM clarification_sessions WHERE normalized_key = ? AND status = 'IN_PROGRESS' ORDER BY created_at DESC LIMIT 1;",
                (norm_key,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_session(row)

        # If analysis or questions missing, generate them
        if ambiguity_analysis is None:
            from src.ml.deepseek_ambiguity_analyzer import get_deepseek_ambiguity_analyzer
            analyzer = get_deepseek_ambiguity_analyzer()
            ambiguity_analysis = analyzer.analyze_ambiguity(
                original_description=p_desc,
                retrieved_candidates=retrieved_candidates or []
            )

        if generated_questions is None:
            from src.ml.dynamic_question_generator import get_dynamic_question_generator
            generator = get_dynamic_question_generator()
            q_res = generator.generate_questions(
                product_description=p_desc,
                ambiguity_result=ambiguity_analysis,
                retrieved_candidates=retrieved_candidates or []
            )
            generated_questions = q_res.get("questions", [])

        # Create new unique session
        clean_uuid = uuid.uuid4().hex[:12].upper()
        session_id = f"CLAR-{clean_uuid}"
        now = utc_now_iso()

        session = ClarificationSession(
            session_id=session_id,
            product_description=p_desc,
            ambiguity_analysis=ambiguity_analysis,
            generated_questions=generated_questions,
            customer_answers=[],
            status="IN_PROGRESS",
            created_at=now,
            updated_at=now,
            status_history=[
                {"from_status": None, "to_status": "IN_PROGRESS", "timestamp": now, "reason": "Session initialized"}
            ],
        )
        self._save_session(session)
        logger.info(f"Initialized clarification session {session_id} for '{p_desc}'")
        return session

    def get_session(self, session_id: str) -> Optional[ClarificationSession]:
        """Retrieves session by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM clarification_sessions WHERE session_id = ?;", (session_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_session(row)
        return None

    def record_answers(
        self,
        session_id: str,
        answers: List[Dict[str, Any]]
    ) -> ClarificationSession:
        """
        Records or updates answers for the session.
        Validates question IDs and preserves unknown states explicitly.
        """
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Clarification session '{session_id}' not found.")

        valid_qids = {q["question_id"] for q in session.generated_questions}
        now = utc_now_iso()

        existing_answers_map = {a["question_id"]: a for a in session.customer_answers}

        for ans in answers:
            if not isinstance(ans, dict):
                continue
            qid = str(ans.get("question_id", "")).strip()
            if qid not in valid_qids:
                logger.warning(f"Ignored unrecognized question_id '{qid}' for session {session_id}")
                continue

            opt_id = str(ans.get("selected_option_id", "")).strip()
            val = ans.get("selected_value")
            free_text = ans.get("free_text")
            is_unknown = bool(ans.get("is_unknown", False)) or opt_id == "OPT_UNKNOWN" or val == "unknown"

            # Unknown response requirement: keep value null, is_unknown True
            if is_unknown:
                val = None
                opt_id = "OPT_UNKNOWN"
                is_unknown = True

            # Preserve question attribute if provided or lookup from generated questions
            attr = ans.get("attribute")
            if not attr:
                for gq in session.generated_questions:
                    if gq.get("question_id") == qid:
                        attr = gq.get("attribute")
                        break

            existing_answers_map[qid] = {
                "question_id": qid,
                "attribute": attr,
                "selected_option_id": opt_id,
                "selected_value": val,
                "free_text": free_text,
                "is_unknown": is_unknown,
                "answered_at": ans.get("answered_at") or now
            }

        session.customer_answers = list(existing_answers_map.values())
        session.updated_at = now
        self._save_session(session)
        return session

    def transition_status(
        self,
        session_id: str,
        new_status: str,
        reason: str = "",
        session: Optional[ClarificationSession] = None
    ) -> ClarificationSession:
        """Enforces lifecycle status transitions and audit history."""
        if session is None:
            session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Clarification session '{session_id}' not found.")

        target_status = str(new_status).upper().strip()
        if target_status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid status '{new_status}'. Allowed: {ALLOWED_STATUSES}")

        now = utc_now_iso()
        old_status = session.status

        # Transition audit
        session.status_history.append({
            "from_status": old_status,
            "to_status": target_status,
            "timestamp": now,
            "reason": reason or f"Transitioned from {old_status} to {target_status}"
        })
        session.status = target_status
        session.updated_at = now

        if target_status == "SUBMITTED" and not session.submitted_at:
            session.submitted_at = now

        self._save_session(session)
        return session

    def enrich_and_reclassify(
        self,
        session_id: str,
        answers: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[ClarificationSession, Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Controlled AI-based product description enrichment and reclassification workflow (Day 16).
        1. Validates and saves customer answers.
        2. Guards against concurrent duplicate execution.
        3. Invokes DeepSeekDescriptionEnricher with Prompt HSN_DESCRIPTION_ENRICHMENT v1.0.0.
        4. Executes deterministic FactGroundingValidator.
        5. If valid, runs reclassification through DeepSeekHSNVerifier.verify_item.
        6. Persists enriched description, validation result, and reclassification outcome.
        """
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Clarification session '{session_id}' not found.")

        # Duplicate submission / concurrency guard
        if session.status in ("ENRICHMENT_IN_PROGRESS", "RECLASSIFICATION_IN_PROGRESS"):
            raise RuntimeError(f"Session '{session_id}' is currently processing ({session.status}). Duplicate run prevented.")

        # If already validated and completed, do not re-enrich unnecessarily
        if session.status in ("COMPLETED", "RECLASSIFICATION_COMPLETED") and session.enriched_description and session.reclassification_status == "SUCCESS":
            return session, (session.validation_result or {}), session.verification_result

        # Save answers if provided
        if answers:
            session = self.record_answers(session_id, answers)

        # Validate required questions
        answered_qids = {a["question_id"] for a in session.customer_answers}
        for q in session.generated_questions:
            if q.get("required") and q["question_id"] not in answered_qids:
                raise ValueError(f"Required question '{q['question_id']}' has not been answered.")

        # Transition to SUBMITTED if not already
        if session.status in ("IN_PROGRESS", "SUBMITTED"):
            session = self.transition_status(session_id, "SUBMITTED", reason="Customer submitted responses", session=session)

        # Step A: Enrichment Phase
        session = self.transition_status(session_id, "ENRICHMENT_IN_PROGRESS", reason="Running controlled AI description enrichment", session=session)

        from src.ml.deepseek_description_enricher import get_deepseek_description_enricher
        enricher = get_deepseek_description_enricher()

        enrichment_out = enricher.enrich_description(
            original_description=session.product_description,
            clarification_answers=session.customer_answers
        )

        now = utc_now_iso()
        session.enriched_description = enrichment_out.enriched_description
        session.enrichment_status = enrichment_out.enrichment_status
        session.enrichment_prompt_version = "1.0.0"
        session.enrichment_timestamp = now
        session.validation_result = enrichment_out.model_dump()

        if not enrichment_out.ready_for_reclassification:
            # Fact-grounding failed or contradiction detected
            session.reclassification_status = "BLOCKED"
            target_status = "MANUAL_REVIEW" if enrichment_out.enrichment_status == "MANUAL_REVIEW" else "ENRICHMENT_FAILED"
            session = self.transition_status(
                session_id,
                target_status,
                reason=f"Enrichment validation blocked reclassification: {enrichment_out.validation_reason}",
                session=session
            )
            return session, enrichment_out.model_dump(), None

        # Step B: Reclassification Phase
        session = self.transition_status(session_id, "ENRICHMENT_COMPLETED", reason="Enrichment fact-grounding validated successfully", session=session)
        session = self.transition_status(session_id, "RECLASSIFICATION_IN_PROGRESS", reason="Running HSN Intelligence reclassification on enriched description", session=session)

        try:
            from src.ml.deepseek_hsn_verifier import get_deepseek_hsn_verifier
            verifier = get_deepseek_hsn_verifier()

            # Execute reclassification using verified engine (save_to_store=False preserves Store Isolation)
            v_res = verifier.verify_item(
                query=enrichment_out.enriched_description,
                base_hsn=None,
                save_to_store=False
            )
            session.verification_result = v_res

            v_status = str(v_res.get("status", "")).upper()
            if "AMBIGUOUS" in v_status or v_status == "MANUAL_REVIEW_REQUIRED":
                session.reclassification_status = "AMBIGUOUS"
                session = self.transition_status(session_id, "MANUAL_REVIEW", reason="Reclassification produced ambiguous candidate spread requiring manual review", session=session)
            else:
                session.reclassification_status = "SUCCESS"
                session = self.transition_status(session_id, "COMPLETED", reason="Reclassification completed with verified tariff code", session=session)

            return session, enrichment_out.model_dump(), v_res
        except Exception as e:
            logger.error(f"Reclassification error for session {session_id}: {e}")
            session.reclassification_status = "ERROR"
            session = self.transition_status(session_id, "FAILED", reason=f"Reclassification error: {str(e)}", session=session)
            return session, enrichment_out.model_dump(), {"status": "FAILED", "error": str(e)}

    def submit_and_verify(
        self,
        session_id: str,
        answers: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[ClarificationSession, Dict[str, Any]]:
        """Legacy submit and verify method delegating to enrich_and_reclassify."""
        session, _, v_res = self.enrich_and_reclassify(session_id, answers)
        return session, (v_res or {})

    def _save_session(self, session: ClarificationSession):
        """Persists session into SQLite database."""
        norm_key = normalize_product_key(session.product_description)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO clarification_sessions (
                    session_id, schema_version, product_description, normalized_key,
                    ambiguity_analysis, generated_questions, customer_answers,
                    status, created_at, updated_at, submitted_at,
                    status_history, verification_result,
                    enriched_description, enrichment_status, enrichment_prompt_version,
                    enrichment_timestamp, validation_result, reclassification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session.session_id,
                    session.schema_version,
                    session.product_description,
                    norm_key,
                    json.dumps(session.ambiguity_analysis),
                    json.dumps(session.generated_questions),
                    json.dumps(session.customer_answers),
                    session.status,
                    session.created_at,
                    session.updated_at,
                    session.submitted_at,
                    json.dumps(session.status_history),
                    json.dumps(session.verification_result) if session.verification_result else None,
                    session.enriched_description,
                    session.enrichment_status,
                    session.enrichment_prompt_version,
                    session.enrichment_timestamp,
                    json.dumps(session.validation_result) if session.validation_result else None,
                    session.reclassification_status,
                ),
            )
            conn.commit()

    def _row_to_session(self, row: sqlite3.Row) -> ClarificationSession:
        """Reconstructs ClarificationSession object from database row."""
        keys = row.keys()
        return ClarificationSession(
            session_id=row["session_id"],
            schema_version=row["schema_version"],
            product_description=row["product_description"],
            ambiguity_analysis=json.loads(row["ambiguity_analysis"]),
            generated_questions=json.loads(row["generated_questions"]),
            customer_answers=json.loads(row["customer_answers"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            submitted_at=row["submitted_at"],
            status_history=json.loads(row["status_history"]),
            verification_result=json.loads(row["verification_result"]) if row["verification_result"] else None,
            enriched_description=row["enriched_description"] if "enriched_description" in keys else None,
            enrichment_status=row["enrichment_status"] if "enrichment_status" in keys else None,
            enrichment_prompt_version=row["enrichment_prompt_version"] if "enrichment_prompt_version" in keys else None,
            enrichment_timestamp=row["enrichment_timestamp"] if "enrichment_timestamp" in keys else None,
            validation_result=json.loads(row["validation_result"]) if ("validation_result" in keys and row["validation_result"]) else None,
            reclassification_status=row["reclassification_status"] if "reclassification_status" in keys else None,
        )


def get_clarification_session_manager() -> ClarificationSessionManager:
    """Returns singleton instance of ClarificationSessionManager."""
    if ClarificationSessionManager._instance is None:
        ClarificationSessionManager._instance = ClarificationSessionManager()
    return ClarificationSessionManager._instance
