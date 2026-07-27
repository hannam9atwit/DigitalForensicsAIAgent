"""
gui_v2/main_window.py

The application shell: menu bar, sidebar, screen stack, explainer rail, status
bar — and the wiring between them.

The window owns app-level state (which case is open, which screen is showing)
and resolves navigation. Screens own their own selection. When a screen's
selection changes it emits a RailPayload and the window hands it to the rail;
when a screen wants to send the user somewhere it emits navigate(id, arg) and
the window resolves it. Nothing else knows the rail exists.

Three states: no case (launch), analyzing (pipeline progress), case open (the
full shell). The sidebar and rail only exist in the third — with no case there
is nothing for them to say.
"""

import os

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStackedWidget,
    QStatusBar, QMessageBox, QProgressDialog, QFileDialog, QFrame,
)

from . import theme, widgets as w, content, thread_registry
from .case_model import empty_case
from .intake_dialog import IntakeDialog, EVIDENCE_FILTER
from .rail import ExplainerRail, RailPayload
from .sidebar import Sidebar
from .screens import (
    CaseScreen, FindingsScreen, EvidenceScreen, TimelineScreen, ReportScreen,
    ChatScreen, AuditScreen, SettingsScreen, LaunchScreen, AnalyzingScreen,
)

P = theme.GUIDED


class AnalysisWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    log = Signal(str)
    stage = Signal(int)

    def __init__(self, builder, ai_config=None):
        super().__init__()
        self.builder = builder
        self.ai_config = ai_config or {}

    def run(self):
        try:
            # The key travels in memory only — never via the process
            # environment, which child processes would inherit.
            self.builder.analyze(log=self._log, ai_config=self.ai_config)
            self.finished.emit(self.builder)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def _log(self, msg):
        """Map the pipeline's log lines onto the five stages the analyzing
        screen shows, so its progress reflects real work rather than a timer."""
        self.log.emit(msg)
        m = msg.lower()
        if "hashing" in m:
            self.stage.emit(0)
        elif "parsing" in m:
            self.stage.emit(1)
        elif "unified timeline" in m or "interpreted events" in m:
            self.stage.emit(2)
        elif "finding" in m or "rule" in m:
            self.stage.emit(3)
        elif "narrative" in m:
            self.stage.emit(4)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AIRforensics")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        self.builder = None
        self.case = empty_case()
        # Every in-flight BackgroundTask is held here until it signals finished,
        # so a task is never freed (nor overwritten by a later one) mid-run.
        self._bg_tasks = set()

        from . import app_settings
        self.settings = {"examiner": "", "examiner_id": "", "agency": "",
                         "cloud_api_key": "",
                         "ai_provider": "ollama",
                         "ollama_model": "llama3.2:3b"}
        self.settings.update(app_settings.load())
        self.settings["cloud_api_key"] = ""
        self.screens = {}
        self._current = None

        self.setStyleSheet(theme.stylesheet(P))
        self._build_menu()
        self._build_ui()
        self.show_launch()

    # ── shell ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(content.STEPS, content.EXTRAS)
        self.sidebar.navigate.connect(lambda sid: self.go(sid))
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.rail = ExplainerRail()
        self.rail.chip_clicked.connect(self._resolve_ref)
        self.rail.ask_submitted.connect(self._rail_ask)
        root.addWidget(self.rail)

        self.setStatusBar(QStatusBar())
        self._status_right = QLabel("")
        self._status_right.setStyleSheet(
            f"color: {P['text3']}; font-family: {theme.MONO_STACK}; font-size: 10px;")
        self.statusBar().addPermanentWidget(self._status_right)
        self._refresh_status()

    def _build_menu(self):
        mb = self.menuBar()
        # Hold a reference: passing the corner widget as a temporary lets Python
        # drop it before Qt takes ownership, and it is silently destroyed.
        self._corner = self._menu_corner()
        mb.setCornerWidget(self._corner, Qt.TopRightCorner)

        fm = mb.addMenu("File")
        fm.addAction(QAction("New Case…", self, triggered=self.new_case,
                             shortcut=QKeySequence.New))
        fm.addAction(QAction("Open Case…", self, triggered=self.open_case_history,
                             shortcut=QKeySequence.Open))
        fm.addAction(QAction("Add Evidence…", self, triggered=self.add_evidence))
        fm.addAction(QAction("Save Case", self, triggered=self.save_case,
                             shortcut=QKeySequence.Save))
        fm.addSeparator()
        fm.addAction(QAction("Export Report PDF…", self, triggered=self.export_report))
        fm.addAction(QAction("Export Selected Evidence…", self,
                             triggered=lambda: self._export_evidence(None)))
        fm.addSeparator()
        fm.addAction(QAction("Exit", self, triggered=self.close))

        cm = mb.addMenu("Case")
        cm.addAction(QAction("Run / Re-run Analysis", self, triggered=self.run_analysis))
        cm.addAction(QAction("Re-verify Hashes", self, triggered=self.verify_hashes))
        cm.addSeparator()
        cm.addAction(QAction("Open Demo Case", self, triggered=self.open_demo))

        vm = mb.addMenu("View")
        for i, (sid, label, _sub) in enumerate(content.STEPS, start=1):
            vm.addAction(QAction(label, self, shortcut=QKeySequence(str(i)),
                                 triggered=lambda _=False, s=sid: self.go(s)))

        tm = mb.addMenu("Tools")
        tm.addAction(QAction("Ask the AI", self, triggered=lambda: self.go("chat")))
        tm.addAction(QAction("Audit Trail", self, triggered=lambda: self.go("audit")))
        tm.addAction(QAction("Settings", self, triggered=lambda: self.go("settings")))

        hm = mb.addMenu("Help")
        hm.addAction(QAction("About", self, triggered=self._about))

    def _menu_corner(self):
        """Right side of the menu bar: the open case, then the offline state."""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 12, 0)
        h.setSpacing(14)
        self._menu_case = QLabel("")
        self._menu_case.setStyleSheet(
            f"color: {P['text3']}; font-family: {theme.MONO_STACK}; font-size: 10px;")
        h.addWidget(self._menu_case)
        offline = QLabel("● OFFLINE · LOCAL AI")
        offline.setStyleSheet(
            f"color: {P['good']}; font-family: {theme.MONO_STACK}; "
            f"font-size: 10px; font-weight: 600;")
        h.addWidget(offline)
        return box

    # ── app states ────────────────────────────────────────────────────────────

    def _clear_stack(self):
        while self.stack.count():
            wdg = self.stack.widget(0)
            self.stack.removeWidget(wdg)
            wdg.deleteLater()
        self.screens.clear()

    def show_launch(self):
        self._clear_stack()
        self.sidebar.hide()
        self.rail.hide()
        launch = LaunchScreen(self._recent_cases())
        launch.new_case.connect(self.new_case)
        launch.open_case.connect(self._open_recent)
        self.stack.addWidget(launch)
        self._current = None
        self._refresh_status()

    def _recent_cases(self):
        """Real saved cases, newest first, shaped for the history card.

        The demo case is appended when the machine has no cases yet, so a fresh
        install has something to open rather than an empty panel.
        """
        out = []
        try:
            from .case_store import list_cases
            for c in list_cases():
                n_f = c.get("findings", 0)
                n_e = c.get("evidence", 0)
                artifacts = f"{n_e} artifact{'' if n_e == 1 else 's'}"
                findings = f"{n_f} finding{'' if n_f == 1 else 's'}"
                meta = (f"Saved {c.get('saved','—')} · {findings} · {artifacts}"
                        if c.get("analyzed") else
                        f"Saved {c.get('saved','—')} · not yet analyzed · {artifacts}")
                out.append({
                    "id": c.get("id", "—"),
                    "title": c.get("title", "Untitled"),
                    "meta": meta,
                    "risk": findings.upper() if c.get("analyzed") else "NEW",
                    "hot": n_f > 0,
                    "path": c.get("path"),
                })
        except Exception:
            pass
        if not out:
            demo = dict(content.RECENT_CASES[0])
            demo["path"] = "__demo__"
            demo["meta"] = "Demo fixture · 7 findings · 5 artifacts"
            out.append(demo)
        return out

    def _open_recent(self, path):
        if path == "__demo__":
            self.open_demo()
        elif path:
            self._load_case_file(path)
        else:
            self.open_case_history()

    def open_demo(self):
        self.builder = None
        self.case = content.demo_case()
        self._enter_case()
        self.go("case")
        self.statusBar().showMessage(
            "Demo case loaded — DEMO-001 (fixture data, no real evidence)", 6000)

    def _enter_case(self):
        """Build the case screens and show the full shell."""
        self._clear_stack()
        self.sidebar.show()
        self.rail.show()

        self.screens = {
            "case": CaseScreen(self.case),
            "evidence": EvidenceScreen(self.case),
            "timeline": TimelineScreen(self.case),
            "findings": FindingsScreen(self.case),
            "report": ReportScreen(self.case),
            "chat": ChatScreen(self.case),
            "audit": AuditScreen(self.case),
            "settings": SettingsScreen(self.case, self.settings),
        }
        ai_config = self._ai_config()
        for s in self.screens.values():
            s.ai_config = ai_config
            self.stack.addWidget(s)
            s.rail_changed.connect(self.rail.set_payload)
            s.navigate.connect(self.go)

        self.screens["settings"].changed.connect(self._settings_changed)
        self.screens["report"].export_requested.connect(self.export_report)
        self.screens["report"].narrative_updated.connect(self._narrative_regenerated)
        self.screens["chat"].asked.connect(self._log_question)

        self._refresh_sidebar()
        self._refresh_status()

    def _ai_config(self) -> dict:
        """The user's engine choice, in the shape every AI module accepts."""
        return {
            "provider": self.settings.get("ai_provider", "ollama"),
            "model": self.settings.get("ollama_model", "llama3.2:3b"),
            "api_key": self.settings.get("cloud_api_key", ""),
        }

    def _settings_changed(self, settings: dict):
        from . import app_settings
        app_settings.save(settings)
        ai_config = self._ai_config()
        for screen in self.screens.values():
            screen.ai_config = ai_config

    def _narrative_regenerated(self, payload):
        """The report screen re-drafted the narrative. Fold it into the cached
        analysis and re-save, so the fresh draft survives a reopen rather than
        being lost the moment the examiner leaves the tab."""
        if self.builder and isinstance(self.builder.analysis, dict):
            self.builder.analysis["narrative"] = payload
            try:
                from .case_store import save_case
                save_case(self.builder)
            except Exception:
                pass
        self.statusBar().showMessage("Narrative re-drafted", 4000)

    def show_analyzing(self):
        self._clear_stack()
        self.sidebar.hide()
        self.rail.hide()
        self._analyzing = AnalyzingScreen()
        self.stack.addWidget(self._analyzing)
        self._refresh_status(analyzing=True)

    # ── navigation ────────────────────────────────────────────────────────────

    def go(self, sid, arg=None):
        if sid not in self.screens:
            return
        self.stack.setCurrentWidget(self.screens[sid])
        self.sidebar.set_active(sid)
        self._current = sid
        self.screens[sid].on_show(arg)

    def _rail_ask(self, question):
        """Answer a rail mini-chat question with the same async engine the
        full chat screen uses, so any page can query the model in place."""
        from .ai_worker import SurfaceJob
        job = SurfaceJob(self._ai_config())
        job.answer_ready.connect(self._rail_answer_ready)
        self._rail_ask_job = job
        job.run("ask", token="rail", fallback="",
                question=question, case=self.case)

    def _rail_answer_ready(self, _token, answer):
        if answer and answer.get("paras"):
            text = "\n\n".join(answer["paras"])
            if answer.get("uncertain"):
                text += f"\n\nUncertain: {answer['uncertain']}"
        else:
            from core import ollama_runtime
            health = ollama_runtime.readiness(
                self._ai_config().get("model", "llama3.2:3b"))
            if not health["installed"]:
                text = ("Local AI isn't installed. Set it up in Settings to "
                        "ask questions.")
            elif not health["running"]:
                text = ("Local AI isn't running. Open Settings and re-check to "
                        "start it.")
            elif not health["model_ready"]:
                text = "The model isn't downloaded yet. Set it up in Settings."
            else:
                text = ("No answer came back. Try rephrasing, or use the full "
                        "Ask the AI screen.")
        self.rail.show_mini_answer(text)

    def _resolve_ref(self, ref):
        """Rail chips carry a bare reference; the window knows where it points."""
        if ref == "TL":
            self.go("timeline", "Jun 3 19:18:47")
        elif ref.startswith("F-"):
            self.go("findings", ref)
        elif ref.startswith("EV-"):
            self.go("evidence", ref)

    # ── sidebar / status ──────────────────────────────────────────────────────

    def _refresh_sidebar(self):
        meta = self.case.get("caseMeta", {})
        ev = self.case.get("evidence", [])
        f = self.case.get("findings", [])
        verified = sum(1 for e in ev if e.get("verified"))
        crit = sum(1 for x in f if str(x.get("sev", "")).upper() == "CRITICAL")
        events = meta.get("pipeline", {}).get("eventsParsed", 0)

        risk = meta.get("riskScore", 0)
        risk_label = meta.get("riskLabel", "—")
        self.sidebar.set_sub("case", f"Risk {risk} · {str(risk_label).lower()}")
        self.sidebar.set_sub(
            "evidence",
            f"{len(ev)} artifact{'' if len(ev) == 1 else 's'} · {verified} verified")
        self.sidebar.set_sub("timeline",
                             f"{events:,} event{'' if events == 1 else 's'}")
        self.sidebar.set_sub(
            "findings",
            f"{len(f)} finding{'' if len(f) == 1 else 's'} · {crit} critical"
            if f else "No findings")
        self.sidebar.set_sub("report", "Draft ready" if f else "Nothing to report")
        self.sidebar.risk.set_risk(
            risk, risk_label,
            meta.get("riskCaption") or self._risk_caption(f))

    def _risk_caption(self, findings):
        crit = sum(1 for x in findings if str(x.get("sev", "")).upper() == "CRITICAL")
        if crit:
            return f"Driven by {crit} critical finding{'s' if crit > 1 else ''}."
        if findings:
            return f"Based on {len(findings)} finding(s) below critical."
        return "No findings crossed the reporting threshold."

    def _refresh_status(self, analyzing=False):
        sb = self.statusBar()
        if analyzing:
            sb.showMessage("● PIPELINE RUNNING")
            self._status_right.setText("")
            self._menu_case.setText("")
            return
        if not self.case.get("loaded"):
            sb.showMessage("NO CASE LOADED — FILE ▸ NEW CASE TO BEGIN")
            self._status_right.setText("")
            self._menu_case.setText("")
            return

        meta = self.case.get("caseMeta", {})
        ev = self.case.get("evidence", [])
        verified = sum(1 for e in ev if e.get("verified"))
        sb.showMessage("● READ-ONLY EVIDENCE   ·   NOTHING IS EXECUTED   ·   "
                       "CHAIN OF CUSTODY INTACT")
        self._status_right.setText(
            f"SHA-256 · {len(ev)} REGISTERED · {verified} VERIFIED     OFFLINE")
        self._menu_case.setText(f"{meta.get('id','—')} · {meta.get('title','')}")

    # ── case lifecycle ────────────────────────────────────────────────────────

    def new_case(self):
        dlg = IntakeDialog(self, self.settings)
        if not dlg.exec():
            return
        # Read the dialog's Qt fields here, on the UI thread; hash the files
        # (the multi-GB, multi-minute part) off-thread so the window never
        # freezes during intake.
        builder = dlg.make_builder()
        paths = dlg.file_paths()

        def hash_files(progress):
            for p in paths:
                progress(f"Hashing {os.path.basename(p)}…")
                builder.add_evidence(p)
            return builder

        self._run_bg("Hashing evidence on intake…", hash_files, self._new_case_hashed)

    def _new_case_hashed(self, builder):
        self.builder = builder
        self.case = builder.to_case()
        self._enter_case()
        self.go("evidence")
        if QMessageBox.question(
                self, "Run analysis",
                f"{len(builder.evidence)} artifact(s) hashed and registered.\n"
                "Run the full analysis pipeline now?") == QMessageBox.Yes:
            self.run_analysis()

    def add_evidence(self):
        if not self.builder:
            QMessageBox.information(self, "No case",
                                    "Create a case first (File ▸ New Case).")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Evidence Files", "", EVIDENCE_FILTER)
        if not paths:
            return

        builder = self.builder

        def hash_files(progress):
            for p in paths:
                progress(f"Hashing {os.path.basename(p)}…")
                builder.add_evidence(p)
            return None

        self._run_bg("Hashing evidence on intake…", hash_files,
                     lambda _: self._after_add_evidence())

    def _after_add_evidence(self):
        self.case = self.builder.to_case()
        self._enter_case()
        self.go("evidence")

    def run_analysis(self):
        if not self.builder or not self.builder.evidence:
            QMessageBox.information(self, "Nothing to analyze",
                                    "Create a case and add evidence first.")
            return
        self.show_analyzing()
        # Local refs, not self.thread/self.worker: a second run must never
        # overwrite (and so free) a thread that is still running. thread_registry
        # keeps both alive until the thread's finished() signal fires.
        thread = QThread()
        worker = AnalysisWorker(self.builder, self._ai_config())
        worker.moveToThread(thread)
        worker.log.connect(self._analysis_log)
        worker.stage.connect(lambda n: self._analyzing.set_step(n))
        worker.finished.connect(self._analysis_done)
        worker.error.connect(self._analysis_error)
        thread.started.connect(worker.run)
        # Free the worker on the worker thread while its event loop is still
        # running, then stop the loop; the thread deletes itself via the
        # registry on finished().
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread_registry.track(thread, worker)
        thread.start()

    def _analysis_log(self, msg):
        self.statusBar().showMessage(f"● PIPELINE RUNNING — {msg}")
        if getattr(self, "_analyzing", None):
            self._analyzing.set_log(msg)

    def _analysis_done(self, builder):
        self.builder = builder
        self.case = builder.to_case()
        self._enter_case()
        self.go("case")
        try:
            from .case_store import save_case
            save_case(self.builder)
        except Exception:
            pass
        self.statusBar().showMessage(
            f"Analysis complete — {self.case['caseMeta']['id']} — "
            f"{len(self.case['findings'])} findings", 8000)

    def _analysis_error(self, msg):
        # Keep the case open on Evidence rather than dropping the examiner back
        # to an empty launch screen — the artifacts are still registered.
        if self.builder:
            self.case = self.builder.to_case()
            self._enter_case()
            self.go("evidence")
        else:
            self.show_launch()
        QMessageBox.critical(self, "Analysis failed", msg.split("\n")[0])
        self.statusBar().showMessage("Analysis failed — evidence is still registered",
                                     8000)

    def verify_hashes(self):
        if not self.builder:
            QMessageBox.information(self, "No case", "Open a real case first.")
            return
        # Re-hashing every registered image is the single heaviest blocker in
        # the app; run it off-thread behind the progress dialog.
        builder = self.builder

        def reverify(progress):
            progress("Re-hashing registered evidence…")
            return builder.reverify()

        self._run_bg("Re-verifying evidence hashes…", reverify, self._after_verify)

    def _after_verify(self, results):
        self.case = self.builder.to_case()
        self._enter_case()
        self.go("evidence")
        ok = sum(1 for v in results.values() if v)
        self.statusBar().showMessage(
            f"Re-verified {ok}/{len(results)} artifact(s) OK", 5000)

    # ── persistence ───────────────────────────────────────────────────────────

    def save_case(self):
        if not self.builder:
            QMessageBox.information(self, "No case", "Create a case first.")
            return
        from .case_store import save_case
        path = save_case(self.builder)
        self.case = self.builder.to_case()
        self.statusBar().showMessage(f"Case saved — {path}", 6000)

    def open_case_history(self):
        from .case_history import CaseHistoryDialog
        dlg = CaseHistoryDialog(self)
        if dlg.exec() and dlg.selected_path:
            self._load_case_file(dlg.selected_path)

    def _load_case_file(self, path):
        from .case_store import load_case
        # Unzipping and JSON-parsing a saved case (all events + findings) can
        # take seconds for a large case; do it off-thread.
        self._run_bg(
            "Opening case…",
            lambda progress: load_case(path),
            self._case_loaded,
            on_error=lambda msg: QMessageBox.critical(self, "Open failed", msg))

    def _case_loaded(self, builder):
        self.builder = builder
        self.case = builder.to_case()
        self._enter_case()
        self.go("case" if self.case.get("findings") else "evidence")
        self.statusBar().showMessage(
            f"Opened case {self.case['caseMeta']['id']}", 5000)

    # ── report / evidence export ──────────────────────────────────────────────

    def export_report(self):
        if not self.case.get("loaded"):
            QMessageBox.information(self, "No case", "Open a case first.")
            return
        default = f"{self.case['caseMeta']['id']}_report.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", default, "PDF files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        # The reportlab import is cheap; keep its specific "missing" guidance on
        # the UI thread, then build the document (which loops over every event
        # and writes the file) off-thread.
        try:
            from .report_pdf import generate_report
        except ImportError:
            QMessageBox.warning(self, "reportlab missing",
                                "PDF reports need reportlab:\n\npip install reportlab")
            return

        rep = self.screens.get("report")
        case_for_pdf = dict(self.case)
        if rep:
            # Take the screen's own list: it carries the examiner's inclusions
            # *and* the report order, which a re-filter of self.case would drop.
            case_for_pdf["findings"] = rep.included_findings()
            case_for_pdf["examinerNotes"] = rep.notes

        self._run_bg(
            "Building PDF report…",
            lambda progress: generate_report(case_for_pdf, path),
            lambda _r: self._report_exported(path, rep, len(case_for_pdf["findings"])),
            on_error=lambda msg: QMessageBox.critical(self, "Report failed", msg))

    def _report_exported(self, path, rep, finding_count):
        self._audit("REPORT_EXPORTED",
                    f"{os.path.basename(path)} · {finding_count} findings included",
                    kind="user")
        if rep:
            rep.mark_exported(os.path.basename(path))
        self.statusBar().showMessage(f"Report exported — {path}", 6000)
        if QMessageBox.question(self, "Report ready",
                                f"Report saved:\n{path}\n\nOpen it now?") == \
                QMessageBox.Yes:
            self._open_path(path)

    def _export_evidence(self, selected):
        if not self.builder or not self.builder.evidence:
            QMessageBox.information(self, "No evidence",
                                    "Open a real case with evidence first.")
            return
        items = selected or self.builder.evidence
        dest = QFileDialog.getExistingDirectory(self, "Choose export destination")
        if not dest:
            return
        from .evidence_export import export_evidence
        meta = self.case["caseMeta"]
        # Copying every original byte-for-byte and re-hashing each copy is
        # ~2× the total evidence size in I/O; run it off-thread.
        self._run_bg(
            "Copying & re-hashing evidence…",
            lambda progress: export_evidence(items, dest, meta, log=progress),
            lambda res: self._evidence_exported(res, dest))

    def _evidence_exported(self, res, dest):
        self.builder._log(
            "EVIDENCE_EXPORTED",
            f"{res['ok']}/{res['total']} artifact(s) exported to {dest}",
            who=self.settings.get("examiner") or "examiner")
        self.case = self.builder.to_case()
        QMessageBox.information(
            self, "Export complete",
            f"Exported {res['ok']}/{res['total']} artifact(s).\n"
            f"All copies re-hashed against intake SHA-256.")

    # ── audit ─────────────────────────────────────────────────────────────────

    def _audit(self, act, detail, kind="user"):
        """Append to the trail. The demo case holds dicts; a real case's trail
        lives on the builder and is re-read through to_case()."""
        who = self.settings.get("examiner") or self.case.get(
            "caseMeta", {}).get("examiner", "examiner")
        if self.builder:
            self.builder._log(act, detail, who=who)
            self.case = self.builder.to_case()
            if "audit" in self.screens:
                self.screens["audit"].case = self.case
        else:
            import datetime
            self.case.setdefault("audit", []).append({
                "ts": datetime.datetime.now().strftime("%b %d %H:%M:%S"),
                "who": who, "act": act, "detail": detail, "kind": kind,
            })
        if "audit" in self.screens:
            self.screens["audit"].refresh()

    def _log_question(self, text):
        self._audit("AI_QUESTION", f"Examiner asked: “{text[:70]}”", kind="user")

    # ── misc ──────────────────────────────────────────────────────────────────

    def _about(self):
        QMessageBox.about(
            self, "AIRforensics",
            "AIRforensics\n\n"
            "An offline digital forensics investigation platform.\n"
            "Evidence is hashed on intake, opened read-only, and never executed.\n"
            "The AI narrative runs on a local model by default.")

    def _open_path(self, path):
        import sys, subprocess
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _progress(self, text):
        p = QProgressDialog(text, None, 0, 0, self)
        p.setWindowModality(Qt.WindowModal)
        p.setMinimumDuration(0)
        p.setCancelButton(None)
        p.show()
        return p

    def _run_bg(self, message, fn, on_done, on_error=None):
        """Run a blocking callable off the UI thread behind a live modal
        progress dialog, then hand its result to on_done back on the UI thread.

        This is what keeps intake hashing, evidence copy/export, PDF building
        and case opening from freezing the window: the dialog animates and the
        app stays painted while the work runs. The dialog stays modal, so the
        user still waits for the operation exactly as before — only the freeze
        is gone.

        fn(progress) does the work and returns a value; progress(str) posts
        status lines to the dialog. on_done(value) runs on success; on_error(str)
        on failure (a critical message box by default).
        """
        from .task_worker import BackgroundTask
        prog = self._progress(message)

        def _on_done(result):
            prog.close()
            on_done(result)

        def _on_fail(msg):
            prog.close()
            if on_error:
                on_error(msg)
            else:
                QMessageBox.critical(self, "Operation failed", msg)

        task = BackgroundTask(fn)
        task.progress.connect(prog.setLabelText)
        task.done.connect(_on_done)
        task.failed.connect(_on_fail)
        # Retain until the worker thread has fully finished — released on
        # finished(), never on done/failed, so the object outlives its thread.
        self._bg_tasks.add(task)
        task.finished.connect(lambda t=task: self._bg_tasks.discard(t))
        task.start()

    def closeEvent(self, event):
        """Stop and join any live QThread workers before the window (and then
        the interpreter) tears down, so a still-running thread is never
        collected. Daemon-thread jobs (BackgroundTask, viewer, ai) die with the
        process on their own and need no join."""
        thread_registry.shutdown()
        super().closeEvent(event)
