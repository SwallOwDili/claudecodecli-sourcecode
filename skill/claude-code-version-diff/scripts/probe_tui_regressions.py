#!/usr/bin/env python3

import argparse
import datetime
import fcntl
import hashlib
import http.server
import json
import os
import platform
import pty
import re
import select
import signal
import sys
import struct
import subprocess
import tempfile
import termios
import threading
import time
from pathlib import Path


PROMPT = "TUI_PERMISSION_PROBE_MARKER"
FIRST_READ_ID = "toolu_tui_permission_first_read"
FIRST_ID = "toolu_tui_permission_first"
SECOND_READ_ID = "toolu_tui_permission_second_read"
SECOND_ID = "toolu_tui_permission_second"
ANSI_RE = re.compile(
    rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[PX^_].*?\x1b\\|[@-_])",
    re.DOTALL,
)


class ScenarioComplete(Exception):
    pass


def sse_events(model, blocks, stop_reason):
    message_id = f"msg_tui_{int(time.time() * 1000)}"
    events = [
        ("message_start", {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 0},
            },
        })
    ]
    for index, block in enumerate(blocks):
        if block["type"] == "tool_use":
            events.append(("content_block_start", {
                "type": "content_block_start",
                "index": index,
                "content_block": {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "input": {},
                },
            }))
            events.append(("content_block_delta", {
                "type": "content_block_delta",
                "index": index,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(block["input"]),
                },
            }))
        else:
            events.append(("content_block_start", {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "text", "text": ""},
            }))
            events.append(("content_block_delta", {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": block["text"]},
            }))
        events.append(("content_block_stop", {
            "type": "content_block_stop",
            "index": index,
        }))
    events.extend([
        ("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 20},
        }),
        ("message_stop", {"type": "message_stop"}),
    ])
    return events


def has_tool_result(body, tool_id):
    return f'"tool_use_id":"{tool_id}"' in json.dumps(body, separators=(",", ":"))


class State:
    def __init__(self, first_file, second_file):
        self.first_file = first_file
        self.second_file = second_file
        self.main_bodies = []
        self.lock = threading.Lock()


def handler_factory(state):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            raw = self.rfile.read(length)
            if not self.path.startswith("/v1/messages"):
                self.send_response(404)
                self.end_headers()
                return
            body = json.loads(raw)
            text = json.dumps(body, separators=(",", ":"))
            tool_names = {tool.get("name") for tool in body.get("tools", [])}
            is_initial = PROMPT in text and {"Read", "Edit"}.issubset(tool_names)
            is_main = {"Read", "Edit"}.issubset(tool_names) and (
                is_initial
                or FIRST_READ_ID in text
                or FIRST_ID in text
                or SECOND_READ_ID in text
                or SECOND_ID in text
            )
            if not is_main:
                events = sse_events(
                    body.get("model", "claude-probe"),
                    [{"type": "text", "text": "AUXILIARY_OK"}],
                    "end_turn",
                )
            else:
                with state.lock:
                    state.main_bodies.append(body)
                model = body.get("model", "claude-probe")
                if not has_tool_result(body, FIRST_READ_ID):
                    events = sse_events(model, [{
                        "type": "tool_use",
                        "id": FIRST_READ_ID,
                        "name": "Read",
                        "input": {"file_path": str(state.first_file)},
                    }], "tool_use")
                elif not has_tool_result(body, FIRST_ID):
                    events = sse_events(model, [{
                        "type": "tool_use",
                        "id": FIRST_ID,
                        "name": "Edit",
                        "input": {
                            "file_path": str(state.first_file),
                            "old_string": "FIRST_ORIGINAL",
                            "new_string": "FIRST_CHANGED",
                        },
                    }], "tool_use")
                elif not has_tool_result(body, SECOND_READ_ID):
                    events = sse_events(model, [{
                        "type": "tool_use",
                        "id": SECOND_READ_ID,
                        "name": "Read",
                        "input": {"file_path": str(state.second_file)},
                    }], "tool_use")
                elif not has_tool_result(body, SECOND_ID):
                    events = sse_events(model, [{
                        "type": "tool_use",
                        "id": SECOND_ID,
                        "name": "Edit",
                        "input": {
                            "file_path": str(state.second_file),
                            "old_string": "SECOND_ORIGINAL",
                            "new_string": "SECOND_CHANGED",
                        },
                    }], "tool_use")
                else:
                    events = sse_events(
                        model,
                        [{"type": "text", "text": "TUI_PERMISSION_PROBE_DONE"}],
                        "end_turn",
                    )
            payload = "".join(
                f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
                for name, data in events
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("request-id", f"msg_{int(time.time() * 1000)}")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def plain(data):
    return ANSI_RE.sub(b"", data).replace(b"\r", b"").decode("utf-8", "replace")


def compact(output):
    return re.sub(r"\s+", "", output)


def wait_for(master, transcript, predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            transcript.extend(chunk)
        rendered = plain(bytes(transcript))
        if predicate(rendered):
            return rendered
    raise TimeoutError(plain(bytes(transcript))[-4000:])


def resolve_target():
    repo = Path(__file__).resolve().parents[3]
    expected_version = (repo / "VERSION").read_text().strip()
    metadata = json.loads((repo / "analysis/version.json").read_text())
    expected_sha256 = metadata["binary"]["sha256"]
    binary = Path(os.environ.get(
        "CLAUDE_BIN",
        Path.home() / ".local" / "share" / "claude" / "versions" / expected_version,
    ))
    return binary, expected_version, expected_sha256, metadata["binary"]["architecture"]


def run_case(case, binary, expected_version, expected_sha256):
    actual_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual_hash != expected_sha256:
        return {
            "case": case,
            "checks": {"exactBinarySha256": False},
            "error": f"wrong binary hash: {actual_hash}",
            "pass": False,
        }

    root = Path(tempfile.mkdtemp(prefix="claude-tui-permission-probe-"))
    home = root / "home"
    config = root / "config"
    workspace = root / "workspace"
    home.mkdir()
    config.mkdir()
    workspace.mkdir()
    first_file = workspace / "first.txt"
    second_file = workspace / "second.txt"
    first_file.write_text("FIRST_ORIGINAL\n")
    second_file.write_text("SECOND_ORIGINAL\n")
    workspace_real = str(workspace.resolve())
    workspace_private = os.path.realpath(workspace_real)
    project_entries = {
        workspace_real: {"hasTrustDialogAccepted": True},
        workspace_private: {"hasTrustDialogAccepted": True},
    }
    if workspace_real.startswith("/var/"):
        project_entries[f"/private{workspace_real}"] = {"hasTrustDialogAccepted": True}
    global_config = {
        "hasCompletedOnboarding": True,
        "theme": "dark",
        "projects": project_entries,
    }
    (home / ".claude.json").write_text(json.dumps(global_config))
    (config / ".claude.json").write_text(json.dumps(global_config))
    (config / "settings.json").write_text("{}\n")

    state = State(first_file, second_file)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "USERPROFILE": str(home),
        "CLAUDE_CONFIG_DIR": str(config),
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "ANTHROPIC_AUTH_TOKEN": "tui-permission-probe-token",
        "ANTHROPIC_API_KEY": "",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_TELEMETRY": "1",
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "COLUMNS": "120",
        "LINES": "40",
    })
    for name in ("CI", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(name, None)

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    child = subprocess.Popen(
        [
            str(binary),
            "--model", "claude-sonnet-4-5",
            "--tools", "Read,Edit",
            "--permission-mode", "default",
            PROMPT,
        ],
        cwd=workspace,
        env=env,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
        close_fds=True,
    )
    os.close(slave)
    transcript = bytearray()
    result = {
        "target": {
            "version": expected_version,
            "binarySha256": actual_hash,
            "rows": 40,
            "columns": 120,
            "term": env["TERM"],
        },
        "case": case,
        "checks": {},
    }
    try:
        initial = wait_for(
            master,
            transcript,
            lambda output: (
                "Yes,Itrustthisfolder" in compact(output)
                or ("Doyouwantto" in compact(output) and "FIRST_ORIGINAL" in output)
            ),
            30,
        )
        if "Yes,Itrustthisfolder" in compact(initial):
            os.write(master, b"\r")
            wait_for(
                master,
                transcript,
                lambda output: "Doyouwantto" in compact(output) and "FIRST_ORIGINAL" in output,
                30,
            )
        result["checks"]["firstPermissionPromptVisible"] = True

        if case == "quick-arrow-enter":
            os.write(master, b"\x1b[B\r")
            wait_for(master, transcript, lambda output: "TUI_PERMISSION_PROBE_DONE" in output, 20)
            with state.lock:
                arrow_requests = len(state.main_bodies)
            rendered = compact(plain(bytes(transcript)))
            result["checks"].update({
                "quickArrowEnterExecutedFirstEdit": first_file.read_text() == "FIRST_CHANGED\n",
                "quickArrowEnterGrantedSessionEdits": second_file.read_text() == "SECOND_CHANGED\n",
                "secondEditDidNotPrompt": "Doyouwanttomakethisedittosecond.txt?" not in rendered,
                "fiveRequestToolChainCompleted": arrow_requests == 5,
            })
            result["observed"] = {
                "mainRequestCount": arrow_requests,
                "firstFile": first_file.read_text().strip(),
                "secondFile": second_file.read_text().strip(),
            }
            result["pass"] = all(result["checks"].values())
            os.write(master, b"/exit\r")
            deadline = time.monotonic() + 5
            while child.poll() is None and time.monotonic() < deadline:
                try:
                    wait_for(master, transcript, lambda _output: False, 0.2)
                except TimeoutError:
                    pass
            raise ScenarioComplete

        os.write(master, b"\t")
        wait_for(master, transcript, lambda output: "andtellClaudewhattodonext" in compact(output), 10)
        os.write(master, b"COMMENT_MARKER")
        time.sleep(0.4)
        with state.lock:
            before_shift_requests = len(state.main_bodies)
        result["beforeShiftTab"] = {
            "mainRequestCount": before_shift_requests,
            "firstFile": first_file.read_text().strip(),
            "secondFile": second_file.read_text().strip(),
        }

        os.write(master, b"\x1b[Z")
        time.sleep(1.0)
        wait_for(master, transcript, lambda output: "Doyouwantto" in compact(output), 2)
        with state.lock:
            after_shift_requests = len(state.main_bodies)
        result["afterShiftTab"] = {
            "mainRequestCount": after_shift_requests,
            "firstFile": first_file.read_text().strip(),
            "secondFile": second_file.read_text().strip(),
        }
        result["checks"]["shiftTabDidNotSettlePrompt"] = after_shift_requests == before_shift_requests == 2
        result["checks"]["shiftTabDidNotEditFiles"] = (
            first_file.read_text() == "FIRST_ORIGINAL\n"
            and second_file.read_text() == "SECOND_ORIGINAL\n"
        )

        os.write(master, b"\r")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with state.lock:
                count = len(state.main_bodies)
            if count >= 4 and first_file.read_text() == "FIRST_CHANGED\n":
                break
            try:
                wait_for(master, transcript, lambda _output: False, 0.2)
            except TimeoutError:
                pass
        wait_for(master, transcript, lambda output: "SECOND_ORIGINAL" in output, 10)
        with state.lock:
            after_accept_requests = len(state.main_bodies)
        result["afterExplicitAcceptOnce"] = {
            "mainRequestCount": after_accept_requests,
            "firstFile": first_file.read_text().strip(),
            "secondFile": second_file.read_text().strip(),
        }
        result["checks"]["explicitEnterExecutedFirstEdit"] = first_file.read_text() == "FIRST_CHANGED\n"
        result["checks"]["secondEditStillPrompted"] = (
            after_accept_requests == 4 and second_file.read_text() == "SECOND_ORIGINAL\n"
        )

        os.write(master, b"\x1b")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with state.lock:
                count = len(state.main_bodies)
            if "Userrejectedupdate" in compact(plain(bytes(transcript))):
                break
            try:
                wait_for(master, transcript, lambda _output: False, 0.2)
            except TimeoutError:
                pass
        result["checks"]["secondEditDenied"] = second_file.read_text() == "SECOND_ORIGINAL\n"
        result["checks"]["denyStoppedTurnWithoutAnotherRequest"] = count == 4
        wait_for(master, transcript, lambda output: "Userrejectedupdate" in compact(output), 10)
        time.sleep(0.3)
        os.write(master, b"/exit\r")
        deadline = time.monotonic() + 5
        while child.poll() is None and time.monotonic() < deadline:
            try:
                wait_for(master, transcript, lambda _output: False, 0.2)
            except TimeoutError:
                pass
        if child.poll() is None:
            os.write(master, b"\x03")
            time.sleep(0.4)
            os.write(master, b"\x03")
        result["pass"] = all(result["checks"].values())
    except ScenarioComplete:
        pass
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["pass"] = False
    finally:
        try:
            os.write(master, b"\x03\x03")
        except OSError:
            pass
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        try:
            while True:
                chunk = os.read(master, 65536)
                if not chunk:
                    break
                transcript.extend(chunk)
        except OSError:
            pass
        os.close(master)
        server.shutdown()
        server.server_close()
        result["process"] = {"exitStatus": child.returncode}
        result["mainRequestCount"] = len(state.main_bodies)
        result["files"] = {
            "first": first_file.read_text().strip(),
            "second": second_file.read_text().strip(),
        }

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("shift-tab-comment", "quick-arrow-enter"),
        help="run one case instead of the full report",
    )
    args = parser.parse_args()
    binary, expected_version, expected_sha256, binary_architecture = resolve_target()
    version_run = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    node_run = subprocess.run(
        ["node", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    uname_run = subprocess.run(
        ["uname", "-m"],
        capture_output=True,
        text=True,
        check=False,
    )
    cases = (args.case,) if args.case else ("shift-tab-comment", "quick-arrow-enter")
    case_results = {
        case: run_case(case, binary, expected_version, expected_sha256)
        for case in cases
    }
    if args.case:
        output = case_results[args.case]
        print(json.dumps(output, indent=2, ensure_ascii=True))
        raise SystemExit(0 if output.get("pass") else 1)

    shift = case_results["shift-tab-comment"]
    arrow = case_results["quick-arrow-enter"]
    checks = {
        "exactVersion": version_run.returncode == 0
        and version_run.stdout.strip() == f"{expected_version} (Claude Code)",
        "exactBinarySha256": all(
            result.get("target", {}).get("binarySha256") == expected_sha256
            for result in case_results.values()
        ),
        "shiftTabFirstPermissionPromptVisible": shift.get("checks", {}).get("firstPermissionPromptVisible") is True,
        "shiftTabDidNotSettlePrompt": shift.get("checks", {}).get("shiftTabDidNotSettlePrompt") is True,
        "shiftTabDidNotEditFiles": shift.get("checks", {}).get("shiftTabDidNotEditFiles") is True,
        "explicitEnterExecutedFirstEdit": shift.get("checks", {}).get("explicitEnterExecutedFirstEdit") is True,
        "secondEditStillPrompted": shift.get("checks", {}).get("secondEditStillPrompted") is True,
        "secondEditDenied": shift.get("checks", {}).get("secondEditDenied") is True,
        "denyStoppedTurnWithoutAnotherRequest": shift.get("checks", {}).get("denyStoppedTurnWithoutAnotherRequest") is True,
        "quickArrowEnterFirstPermissionPromptVisible": arrow.get("checks", {}).get("firstPermissionPromptVisible") is True,
        "quickArrowEnterExecutedFirstEdit": arrow.get("checks", {}).get("quickArrowEnterExecutedFirstEdit") is True,
        "quickArrowEnterGrantedSessionEdits": arrow.get("checks", {}).get("quickArrowEnterGrantedSessionEdits") is True,
        "secondEditDidNotPrompt": arrow.get("checks", {}).get("secondEditDidNotPrompt") is True,
        "fiveRequestToolChainCompleted": arrow.get("checks", {}).get("fiveRequestToolChainCompleted") is True,
        "shiftTabExitZero": shift.get("process", {}).get("exitStatus") == 0,
        "quickArrowEnterExitZero": arrow.get("process", {}).get("exitStatus") == 0,
    }
    report = {
        "schemaVersion": 1,
        "capturedAt": datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "environment": {
            "platform": sys.platform,
            "arch": uname_run.stdout.strip() if uname_run.returncode == 0 else platform.machine(),
            "pythonProcessArch": platform.machine(),
            "nodeVersion": node_run.stdout.strip() if node_run.returncode == 0 else "unavailable",
            "pythonVersion": platform.python_version(),
            "terminal": {"term": "xterm-256color", "rows": 40, "columns": 120},
        },
        "target": {
            "version": expected_version,
            "binarySha256": expected_sha256,
            "binaryArchitecture": binary_architecture,
        },
        "commands": {
            "shiftTabComment": "$CLAUDE_TARGET --model claude-sonnet-4-5 --tools Read,Edit --permission-mode default TUI_PERMISSION_PROBE_MARKER # PTY 40x120; Tab, COMMENT_MARKER, Shift+Tab, Enter, Escape, /exit",
            "quickArrowEnter": "$CLAUDE_TARGET --model claude-sonnet-4-5 --tools Read,Edit --permission-mode default TUI_PERMISSION_PROBE_MARKER # PTY 40x120; Down+Enter in one write, /exit",
        },
        "input": {
            "isolatedState": "temporary HOME, CLAUDE_CONFIG_DIR and workspace; loopback Messages API; no user configuration",
            "modelToolSequence": [
                "Read($WORKSPACE/first.txt)",
                "Edit($WORKSPACE/first.txt, FIRST_ORIGINAL -> FIRST_CHANGED)",
                "Read($WORKSPACE/second.txt)",
                "Edit($WORKSPACE/second.txt, SECOND_ORIGINAL -> SECOND_CHANGED)",
            ],
            "shiftTabComment": {
                "keystrokes": ["Tab", "COMMENT_MARKER", "Shift+Tab (ESC [ Z)", "Enter", "Escape", "/exit"],
                "expectedScope": "Shift+Tab closes Yes comment input; later Enter grants only the first Edit",
            },
            "quickArrowEnter": {
                "keystrokes": ["Down+Enter in one PTY write", "/exit"],
                "expectedScope": "the newly focused acceptEdits session option settles the prompt",
            },
        },
        "literalOutput": {
            "version": version_run.stdout.strip(),
            "shiftTabComment": {
                "beforeShiftTab": "mainRequestCount=2; first=FIRST_ORIGINAL; second=SECOND_ORIGINAL",
                "afterShiftTab": "mainRequestCount=2; first=FIRST_ORIGINAL; second=SECOND_ORIGINAL",
                "afterExplicitEnter": "mainRequestCount=4; first=FIRST_CHANGED; second=SECOND_ORIGINAL; second permission prompt visible",
                "afterEscape": "mainRequestCount=4; second=SECOND_ORIGINAL; User rejected update",
            },
            "quickArrowEnter": "mainRequestCount=5; first=FIRST_CHANGED; second=SECOND_CHANGED; second permission prompt absent; TUI_PERMISSION_PROBE_DONE",
        },
        "exitStatus": {
            "version": version_run.returncode,
            "shiftTabComment": shift.get("process", {}).get("exitStatus"),
            "quickArrowEnter": arrow.get("process", {}).get("exitStatus"),
        },
        "observed": {
            "shiftTabComment": {
                "beforeShiftTab": shift.get("beforeShiftTab"),
                "afterShiftTab": shift.get("afterShiftTab"),
                "afterExplicitAcceptOnce": shift.get("afterExplicitAcceptOnce"),
                "finalFiles": shift.get("files"),
                "mainRequestCount": shift.get("mainRequestCount"),
            },
            "quickArrowEnter": {
                **arrow.get("observed", {}),
                "finalFiles": arrow.get("files"),
            },
        },
        "coverageBoundary": {
            "multiLineHighlight": "Static offset-to-rendered-line mapping is available, but raw PTY bytes are not a canonical final screen or ANSI-style coordinate model; no runtime claim is made without a terminal emulator and style-position assertions.",
            "vimPanelRestore": "Static external vimMode/savedCursorOffset ownership is available, but the PTY probe does not yet expose an unambiguous mode-and-cursor snapshot across component remount; no runtime claim is made.",
        },
        "checks": checks,
        "pass": all(checks.values()),
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
