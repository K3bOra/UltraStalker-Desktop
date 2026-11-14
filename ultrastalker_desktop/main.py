from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime

from ultrastalker_desktop.runtime import configure_logging, executable_dir, log_dir
from ultrastalker_desktop.single_instance import SingleInstanceGuard

BUILD_SELF_TEST_MARKER = ".ultrastalker-build-self-test"


def _build_self_test_authorized() -> bool:
    """Allow the fingerprinted build self-test only from the release pipeline.

    The builder supplies a fresh nonce both in the process environment and in
    a transient marker beside the packaged executable. The marker is removed
    immediately after the self-test and is never included in the release
    payload. This is an accidental-misuse guard, not an OS security boundary.
    """
    nonce = os.getenv("ULTRASTALKER_RELEASE_BUILD_SELF_TEST", "").strip()
    if len(nonce) < 32:
        return False
    marker = executable_dir() / BUILD_SELF_TEST_MARKER
    try:
        stored = marker.read_text(encoding="ascii").strip()
    except OSError:
        return False
    return stored == nonce


def _install_exception_hook() -> None:
    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        raw_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            from ultrastalker_desktop.support_bundle import sanitize_text
            text = sanitize_text(raw_text)
        except Exception:
            # Never block crash handling because redaction itself had a problem.
            # Fall back to the exception class only rather than persist raw data.
            text = f"{getattr(exc_type, '__name__', 'Exception')}: details redacted\n"
        logging.getLogger("crash").critical("Unhandled exception\n%s", text)
        try:
            from PySide6.QtWidgets import QMessageBox
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            report = log_dir() / f"crash-{stamp}.log"
            report.write_text(text, encoding="utf-8")
            QMessageBox.critical(
                None,
                "Ultra Stalker Desktop",
                "An unexpected error occurred.\n\n"
                f"Crash report:\n{report}",
            )
        except Exception:
            pass

    sys.excepthook = handle


def _self_test(*, build_report: bool = False) -> int:
    from ultrastalker_desktop.diagnostics import (
        run_self_test,
        write_build_self_test_report,
        write_runtime_self_test_report,
    )
    require_release_integrity = bool(not build_report and getattr(sys, "frozen", False))
    passed, report = run_self_test(require_release_integrity=require_release_integrity)
    if build_report:
        write_build_self_test_report(report)
    else:
        write_runtime_self_test_report(report)
    return 0 if passed else 2


def main() -> int:
    if "--self-test-build" in sys.argv:
        if not _build_self_test_authorized():
            logging.getLogger(__name__).error(
                "Build self-test refused outside the release pipeline"
            )
            return 3
        return _self_test(build_report=True)
    if "--self-test" in sys.argv:
        return _self_test(build_report=False)

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    if "--classic" not in sys.argv:
        try:
            # Qt WebEngine must be loaded before the application object exists.
            import PySide6.QtWebEngineWidgets  # noqa: F401
            from ultrastalker_desktop.ui.shell import register_art_scheme

            register_art_scheme()
            QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        except ImportError:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Ultra Stalker Desktop")
    app.setOrganizationName("Ahmed L-HadarY")
    app.setOrganizationDomain("ultrastalker.local")

    instance = SingleInstanceGuard()
    try:
        acquired = instance.acquire()
    except OSError:
        logging.getLogger(__name__).error("Could not initialize single-instance protection")
        QMessageBox.critical(
            None,
            "Ultra Stalker Desktop",
            "Ultra Stalker Desktop could not initialize its local instance lock.\n"
            "The application was not started to protect local profile/settings data.",
        )
        return 4
    if not acquired:
        QMessageBox.information(
            None,
            "Ultra Stalker Desktop",
            "Ultra Stalker Desktop is already running in this Windows session.",
        )
        return 0

    configure_logging()
    _install_exception_hook()
    try:
        window = None
        if "--classic" not in sys.argv:
            try:
                from ultrastalker_desktop.ui.shell import ShellWindow

                window = ShellWindow()
            except ImportError as exc:
                # A build without Qt WebEngine still starts with the classic window.
                logging.getLogger(__name__).warning("Cinematic interface unavailable: %s", type(exc).__name__)
                window = None
        if window is None:
            from ultrastalker_desktop.ui.main_window import UltraStalkerWindow

            window = UltraStalkerWindow()
        window.show()
        return app.exec()
    finally:
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
