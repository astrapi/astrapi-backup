"""
tests/unit/test_scheduler_engine.py

Unit-Tests für core/modules/scheduler/engine.py.

Ziel: Einen vorhandenen Scheduler-Job simulieren und mögliche Fehlerquellen
aufspüren – ohne laufenden Server, ohne externe Dienste.

Die Tests nutzen eine temporäre In-Process-SQLite-DB (via conftest.py) und eine
frische Scheduler-Instanz (kein Modul-Singleton).  Externe Abhängigkeiten wie
notify und activity_log liegen in try/except-Blöcken im Engine-Code und werden
daher beim Fehlen stillschweigend übergangen.
"""

import time

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

def _create_job(scheduler, job_id="test-job", steps=None, enabled=True, cron="0 2 * * *", label=None):
    """Legt einen Job direkt über die Scheduler-API an."""
    scheduler.create_job(
        job_id,
        label or f"Test-Job '{job_id}'",
        cron,
        enabled=enabled,
        steps=steps or [],
    )
    return job_id


def _get_status(job_id="test-job"):
    """Liest den gespeicherten Laufstatus aus der Storage."""
    from astrapi_core.ui.storage import SqliteStorage
    return SqliteStorage("scheduler_status").get(job_id)


# ─────────────────────────────────────────────────────────────────────────────
# _run_job – Ausführungslogik
# ─────────────────────────────────────────────────────────────────────────────

class TestRunJob:

    def test_job_not_in_storage_logs_warning(self, scheduler, caplog):
        """Fehlt ein Job in der Storage, erscheint ein Warning – kein Absturz."""
        scheduler._run_job("nichtvorhanden")
        assert "nicht gefunden" in caplog.text

    def test_job_not_in_storage_does_not_write_status(self, scheduler):
        """Fehlt ein Job in der Storage, wird kein Status-Eintrag angelegt."""
        scheduler._run_job("nichtvorhanden")
        assert _get_status("nichtvorhanden") is None

    # ── Erfolgreiche Ausführung ────────────────────────────────────────────

    def test_single_step_success_calls_action(self, scheduler):
        """Eine registrierte Aktion wird aufgerufen."""
        called = []
        scheduler.register_action("test.run", "Test", lambda: called.append(1))
        _create_job(scheduler, steps=["test.run"])

        scheduler._run_job("test-job")

        assert called == [1], "Aktion wurde nicht aufgerufen"

    def test_single_step_success_status_ok(self, scheduler):
        """Erfolgreicher Schritt → Status 'OK'."""
        scheduler.register_action("test.run", "Test", lambda: None)
        _create_job(scheduler, steps=["test.run"])

        scheduler._run_job("test-job")

        status = _get_status()
        assert status is not None
        assert status["last_status"] == "OK"

    def test_empty_steps_status_ok(self, scheduler):
        """Ein Job ohne Schritte läuft durch und hat Status 'OK'."""
        _create_job(scheduler, steps=[])

        scheduler._run_job("test-job")

        assert _get_status()["last_status"] == "OK"

    # ── Dauer ─────────────────────────────────────────────────────────────

    def test_duration_is_stored_with_unit(self, scheduler):
        """Die Dauer wird im Format '<n>s' gespeichert."""
        scheduler.register_action("test.run", "Test", lambda: None)
        _create_job(scheduler, steps=["test.run"])

        scheduler._run_job("test-job")

        status = _get_status()
        assert "last_duration" in status
        assert status["last_duration"].endswith("s"), (
            f"Unerwartetes Dauer-Format: {status['last_duration']!r}"
        )

    def test_last_run_timestamp_format(self, scheduler):
        """Der Zeitstempel folgt dem Format 'DD.MM.YYYY HH:MM'."""
        import re
        _create_job(scheduler, steps=[])

        scheduler._run_job("test-job")

        ts = _get_status()["last_run"]
        assert re.match(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$", ts), (
            f"Unerwartetes Zeitstempel-Format: {ts!r}"
        )

    # ── Fehlerbehandlung ──────────────────────────────────────────────────

    def test_step_exception_captured_in_status(self, scheduler):
        """Eine Exception im Schritt wird im Status festgehalten, kein Absturz."""
        def boom():
            raise RuntimeError("Festplatte voll")

        scheduler.register_action("test.boom", "Kaputt", boom)
        _create_job(scheduler, steps=["test.boom"])

        scheduler._run_job("test-job")

        status = _get_status()
        assert "Festplatte voll" in status["last_status"]
        assert status["last_status"].startswith("Fehler:")

    def test_unknown_step_captured_in_status(self, scheduler):
        """Ein unbekannter Aktions-Key wird als Fehler im Status vermerkt."""
        _create_job(scheduler, steps=["unbekannte.aktion"])

        scheduler._run_job("test-job")

        status = _get_status()
        assert "Unbekannte Aktion" in status["last_status"]
        assert "unbekannte.aktion" in status["last_status"]

    def test_unknown_step_does_not_call_registered_actions(self, scheduler):
        """Unbekannte Schritte überspringen andere registrierte Aktionen nicht."""
        called = []
        scheduler.register_action("real.step", "Real", lambda: called.append(1))
        # Erster Schritt unbekannt, zweiter bekannt
        _create_job(scheduler, steps=["unbekannt", "real.step"])

        scheduler._run_job("test-job")

        assert called == [1], "Bekannter Schritt wurde nach unbekanntem nicht aufgerufen"

    # ── Multi-Step ────────────────────────────────────────────────────────

    def test_multi_step_all_success(self, scheduler):
        """Mehrere Schritte werden sequenziell aufgerufen."""
        log = []
        scheduler.register_action("step.a", "A", lambda: log.append("a"))
        scheduler.register_action("step.b", "B", lambda: log.append("b"))
        scheduler.register_action("step.c", "C", lambda: log.append("c"))
        _create_job(scheduler, steps=["step.a", "step.b", "step.c"])

        scheduler._run_job("test-job")

        assert log == ["a", "b", "c"], "Schritte nicht in richtiger Reihenfolge"
        assert _get_status()["last_status"] == "OK"

    def test_multi_step_partial_failure_continues(self, scheduler):
        """Schlägt ein Schritt fehl, werden nachfolgende Schritte trotzdem ausgeführt."""
        log = []

        def fail_step():
            raise ValueError("Fehler in Schritt 2")

        scheduler.register_action("step.ok1", "OK1", lambda: log.append("ok1"))
        scheduler.register_action("step.fail", "Fail", fail_step)
        scheduler.register_action("step.ok2", "OK2", lambda: log.append("ok2"))
        _create_job(scheduler, steps=["step.ok1", "step.fail", "step.ok2"])

        scheduler._run_job("test-job")

        assert "ok1" in log
        assert "ok2" in log, "Schritt nach Fehler wurde nicht ausgeführt"
        status = _get_status()
        assert "Fehler in Schritt 2" in status["last_status"]

    def test_multi_step_partial_failure_error_list_in_status(self, scheduler):
        """Mehrere Fehler werden in der Statusmeldung zusammengefasst."""
        def fail_a():
            raise RuntimeError("Fehler A")

        def fail_b():
            raise RuntimeError("Fehler B")

        scheduler.register_action("step.a", "A", fail_a)
        scheduler.register_action("step.b", "B", fail_b)
        _create_job(scheduler, steps=["step.a", "step.b"])

        scheduler._run_job("test-job")

        status_msg = _get_status()["last_status"]
        assert "Fehler A" in status_msg
        assert "Fehler B" in status_msg

    # ── Wiederholter Lauf ─────────────────────────────────────────────────

    def test_second_run_overwrites_status(self, scheduler):
        """Ein zweiter Lauf überschreibt den vorherigen Status."""
        counter = [0]

        def step():
            counter[0] += 1
            if counter[0] == 1:
                raise RuntimeError("Erster Lauf fehlgeschlagen")

        scheduler.register_action("test.step", "Step", step)
        _create_job(scheduler, steps=["test.step"])

        scheduler._run_job("test-job")
        assert _get_status()["last_status"].startswith("Fehler:")

        scheduler._run_job("test-job")
        assert _get_status()["last_status"] == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# trigger_job – Hintergrundausführung
# ─────────────────────────────────────────────────────────────────────────────

class TestTriggerJob:

    def test_trigger_executes_action_in_background(self, scheduler):
        """trigger_job() kehrt sofort zurück; Aktion läuft im Hintergrundthread."""
        done = []
        scheduler.register_action("test.run", "Test", lambda: done.append(1))
        _create_job(scheduler, steps=["test.run"])

        scheduler.trigger_job("test-job")

        deadline = time.time() + 5.0
        while time.time() < deadline and not done:
            time.sleep(0.05)

        assert done == [1], "Aktion wurde vom Hintergrundthread nicht aufgerufen"

    def test_trigger_stores_status(self, scheduler):
        """Nach trigger_job() ist der Status in der Storage gespeichert."""
        scheduler.register_action("test.run", "Test", lambda: None)
        _create_job(scheduler, steps=["test.run"])

        scheduler.trigger_job("test-job")

        deadline = time.time() + 5.0
        while time.time() < deadline:
            if _get_status() is not None:
                break
            time.sleep(0.05)

        status = _get_status()
        assert status is not None
        assert status["last_status"] == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Action Registry
# ─────────────────────────────────────────────────────────────────────────────

class TestActionRegistry:

    def test_register_action_appears_in_list(self, scheduler):
        scheduler.register_action("mod.run", "Modul ausführen", lambda: None)
        actions = scheduler.get_registered_actions()
        assert "mod.run" in actions
        assert actions["mod.run"] == "Modul ausführen"

    def test_multiple_actions_registered(self, scheduler):
        scheduler.register_action("mod.a", "A", lambda: None)
        scheduler.register_action("mod.b", "B", lambda: None)
        actions = scheduler.get_registered_actions()
        assert "mod.a" in actions
        assert "mod.b" in actions

    def test_action_overwrite(self, scheduler):
        """Erneutes Registrieren mit demselben Key überschreibt den alten Eintrag."""
        scheduler.register_action("mod.run", "Alt", lambda: None)
        scheduler.register_action("mod.run", "Neu", lambda: None)
        assert scheduler.get_registered_actions()["mod.run"] == "Neu"

    def test_registered_fn_is_callable(self, scheduler):
        called = []
        scheduler.register_action("mod.run", "Test", lambda: called.append(True))
        scheduler._actions["mod.run"]["fn"]()
        assert called == [True]


# ─────────────────────────────────────────────────────────────────────────────
# Job-CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestJobCRUD:

    def test_create_and_get(self, scheduler):
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=False, steps=[])
        job = scheduler.get_job("j1")
        assert job is not None
        assert job["id"] == "j1"
        assert job["label"] == "Job 1"
        assert job["cron"] == "0 3 * * *"
        assert job["enabled"] is False
        assert job["steps"] == []

    def test_get_nonexistent_returns_none(self, scheduler):
        assert scheduler.get_job("nichtda") is None

    def test_list_returns_all_jobs(self, scheduler):
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=True, steps=[])
        scheduler.create_job("j2", "Job 2", "0 4 * * *", enabled=False, steps=[])
        ids = [j["id"] for j in scheduler.list_jobs()]
        assert "j1" in ids
        assert "j2" in ids

    def test_list_empty(self, scheduler):
        assert scheduler.list_jobs() == []

    def test_update_changes_fields(self, scheduler):
        scheduler.create_job("j1", "Alt", "0 3 * * *", enabled=True, steps=[])
        scheduler.update_job("j1", "Neu", "0 5 * * *", enabled=False, steps=["mod.run"])
        job = scheduler.get_job("j1")
        assert job["label"] == "Neu"
        assert job["cron"] == "0 5 * * *"
        assert job["enabled"] is False
        assert job["steps"] == ["mod.run"]

    def test_delete_removes_job(self, scheduler):
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=True, steps=[])
        scheduler.delete_job("j1")
        assert scheduler.get_job("j1") is None

    def test_delete_removes_status(self, scheduler):
        """Löschen eines Jobs entfernt auch den gespeicherten Laufstatus."""
        scheduler.register_action("test.run", "Test", lambda: None)
        _create_job(scheduler, steps=["test.run"])
        scheduler._run_job("test-job")
        assert _get_status() is not None

        scheduler.delete_job("test-job")
        assert _get_status() is None

    def test_toggle_flips_enabled(self, scheduler):
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=True, steps=[])
        scheduler.toggle_job("j1")
        assert scheduler.get_job("j1")["enabled"] is False
        scheduler.toggle_job("j1")
        assert scheduler.get_job("j1")["enabled"] is True

    def test_create_duplicate_raises(self, scheduler):
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=True, steps=[])
        with pytest.raises(KeyError):
            scheduler.create_job("j1", "Duplikat", "0 3 * * *", enabled=True, steps=[])

    def test_enrich_contains_all_expected_keys(self, scheduler):
        """Der angereicherte Job-Dict enthält alle Felder die die UI erwartet."""
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=True, steps=[])
        job = scheduler.get_job("j1")
        expected_keys = {
            "id", "label", "cron", "enabled", "steps",
            "notify_start", "notify_end",
            "next_run", "last_run", "last_status", "last_duration",
        }
        assert expected_keys <= job.keys(), (
            f"Fehlende Keys: {expected_keys - job.keys()}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# APScheduler-Integration (_sync_jobs)
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncJobs:

    def _start(self, scheduler):
        """Startet den APScheduler und gibt ihn zurück."""
        sch = scheduler._get_sch()
        sch.start()
        return sch

    def test_enabled_job_registered_in_apscheduler(self, scheduler):
        scheduler.create_job("aktiv", "Aktiv", "0 3 * * *", enabled=True, steps=[])
        aps = self._start(scheduler)
        try:
            scheduler._sync_jobs()
            assert aps.get_job("aktiv") is not None
        finally:
            aps.shutdown(wait=False)

    def test_disabled_job_not_registered(self, scheduler):
        scheduler.create_job("inaktiv", "Inaktiv", "0 3 * * *", enabled=False, steps=[])
        aps = self._start(scheduler)
        try:
            scheduler._sync_jobs()
            assert aps.get_job("inaktiv") is None
        finally:
            aps.shutdown(wait=False)

    def test_invalid_cron_does_not_crash(self, scheduler, caplog):
        """Ungültiger Cron-Ausdruck wird als Fehler geloggt, Sync läuft weiter."""
        from astrapi_core.ui.storage import SqliteStorage
        SqliteStorage("scheduler_jobs").create("bad-cron", {
            "label": "Fehlerhafter Cron",
            "cron": "INVALID_CRON",
            "enabled": True,
            "steps": [],
        })
        aps = self._start(scheduler)
        try:
            scheduler._sync_jobs()  # darf nicht werfen
            assert aps.get_job("bad-cron") is None
        finally:
            aps.shutdown(wait=False)

    def test_empty_cron_not_registered(self, scheduler):
        """Leerer Cron-String → Job wird nicht in APScheduler registriert."""
        from astrapi_core.ui.storage import SqliteStorage
        SqliteStorage("scheduler_jobs").create("no-cron", {
            "label": "Kein Cron",
            "cron": "",
            "enabled": True,
            "steps": [],
        })
        aps = self._start(scheduler)
        try:
            scheduler._sync_jobs()
            assert aps.get_job("no-cron") is None
        finally:
            aps.shutdown(wait=False)

    def test_toggle_disable_removes_from_apscheduler(self, scheduler):
        """Nach dem Deaktivieren eines Jobs wird er aus APScheduler entfernt."""
        scheduler.create_job("j1", "Job 1", "0 3 * * *", enabled=True, steps=[])
        aps = self._start(scheduler)
        try:
            scheduler._sync_jobs()
            assert aps.get_job("j1") is not None

            scheduler.toggle_job("j1")  # deaktivieren → _sync_jobs() wird intern aufgerufen
            assert aps.get_job("j1") is None
        finally:
            aps.shutdown(wait=False)
