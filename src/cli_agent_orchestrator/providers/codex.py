"""Codex CLI provider implementation."""

import logging
import re
from typing import Optional

from cli_agent_orchestrator.clients.tmux import tmux_client
from cli_agent_orchestrator.models.terminal import TerminalStatus
from cli_agent_orchestrator.providers.base import BaseProvider
from cli_agent_orchestrator.utils.terminal import wait_for_shell, wait_until_status

logger = logging.getLogger(__name__)

# Regex patterns for Codex output analysis
ANSI_CODE_PATTERN = r"\x1b\[[0-9;]*m"
IDLE_PROMPT_PATTERN = r"(?:❯|›|codex>)"
# Match the prompt only if it appears at the end of the captured output.
IDLE_PROMPT_AT_END_PATTERN = rf"(?:^\s*{IDLE_PROMPT_PATTERN}\s*$)\s*\Z"
IDLE_PROMPT_PATTERN_LOG = r"(?:❯|›)"
ASSISTANT_PREFIX_PATTERN = r"^(?:assistant|codex|agent)\s*:"
USER_PREFIX_PATTERN = r"^You\b"

PROCESSING_PATTERN = r"\b(thinking|working|running|executing|processing|analyzing)\b"
WAITING_PROMPT_PATTERN = r"^(?:Approve|Allow)\b.*\b(?:y/n|yes/no|yes|no)\b"
ERROR_PATTERN = r"^(?:Error:|ERROR:|Traceback \(most recent call last\):|panic:)"

# Newer Codex CLI (v0.9x+) renders a TUI that uses an input line starting with `› ` and a status
# line like `? for shortcuts` / `100% context left`. These do not end the output with a bare prompt
# character, so we need separate detection logic.
TUI_HEADER_PATTERN = r"OpenAI\s+Codex"
TUI_STATUS_BAR_PATTERN = r"\?\s*for shortcuts.*context left"
TUI_PROMPT_LINE_PATTERN = r"^\s*(?:›|❯)\s+\S.*$"
TUI_INTERRUPT_MARKER_PATTERN = r"esc\s+to\s+interrupt"
TUI_RESPONSE_BULLET_PATTERN = r"^\s*•\s*(?!.*esc\s+to\s+interrupt).+"

SHELL_COMMAND_NOT_FOUND_PATTERN = (
    r"(?:command not found: codex|codex: command not found|not found: codex)"
)
CODEX_TERM_DUMB_PATTERN = r'TERM is set to "dumb"\. Refusing to start'


class CodexProvider(BaseProvider):
    """Provider for Codex CLI tool integration."""

    def __init__(
        self,
        terminal_id: str,
        session_name: str,
        window_name: str,
        agent_profile: Optional[str] = None,
    ):
        super().__init__(terminal_id, session_name, window_name)
        self._initialized = False
        self._agent_profile = agent_profile

    def initialize(self) -> bool:
        """Initialize Codex provider by starting codex command."""
        if not wait_for_shell(tmux_client, self.session_name, self.window_name, timeout=10.0):
            raise TimeoutError("Shell initialization timed out after 10 seconds")

        tmux_client.send_keys(self.session_name, self.window_name, "codex")

        if not wait_until_status(self, TerminalStatus.IDLE, timeout=60.0, polling_interval=1.0):
            raise TimeoutError("Codex initialization timed out after 60 seconds")

        self._initialized = True
        return True

    def get_status(self, tail_lines: Optional[int] = None) -> TerminalStatus:
        """Get Codex status by analyzing terminal output."""
        output = tmux_client.get_history(self.session_name, self.window_name, tail_lines=tail_lines)

        if not output:
            return TerminalStatus.ERROR

        clean_output = re.sub(ANSI_CODE_PATTERN, "", output)
        tail_output = "\n".join(clean_output.splitlines()[-40:])

        # Fast-path for common startup failures (e.g., missing codex binary) and non-interactive TERM issues.
        if re.search(SHELL_COMMAND_NOT_FOUND_PATTERN, clean_output, re.IGNORECASE):
            return TerminalStatus.ERROR
        if re.search(CODEX_TERM_DUMB_PATTERN, clean_output, re.IGNORECASE):
            return TerminalStatus.ERROR

        # New Codex TUI mode detection.
        is_tui = bool(
            re.search(TUI_HEADER_PATTERN, clean_output, re.IGNORECASE)
            or re.search(TUI_STATUS_BAR_PATTERN, clean_output, re.IGNORECASE)
        )
        if is_tui:
            # Waiting/error prompts still take precedence if they show up.
            if re.search(WAITING_PROMPT_PATTERN, tail_output, re.IGNORECASE | re.MULTILINE):
                return TerminalStatus.WAITING_USER_ANSWER
            if re.search(ERROR_PATTERN, tail_output, re.IGNORECASE | re.MULTILINE):
                return TerminalStatus.ERROR

            # While Codex is actively working, the UI shows an "esc to interrupt" marker.
            # The verb before it (e.g., Working/Thinking/Analyzing) is not stable.
            if re.search(TUI_INTERRUPT_MARKER_PATTERN, tail_output, re.IGNORECASE):
                return TerminalStatus.PROCESSING

            prompt_re = re.compile(TUI_PROMPT_LINE_PATTERN, re.IGNORECASE)
            bullet_re = re.compile(TUI_RESPONSE_BULLET_PATTERN, re.IGNORECASE)
            lines = clean_output.splitlines()
            prompt_indices = [idx for idx, line in enumerate(lines) if prompt_re.match(line)]

            # Without a visible prompt, assume we're still processing (screen may be mid-refresh).
            if not prompt_indices:
                return TerminalStatus.PROCESSING

            # Heuristic: Codex typically shows a "message prompt" line and then later returns to an
            # "input prompt" line (placeholder). If there are two prompt lines and we see a response
            # bullet between them, treat it as COMPLETED.
            if len(prompt_indices) >= 2:
                prev_prompt = prompt_indices[-2]
                last_prompt = prompt_indices[-1]
                if any(bullet_re.match(line) for line in lines[prev_prompt + 1 : last_prompt]):
                    return TerminalStatus.COMPLETED
                return TerminalStatus.IDLE

            # One prompt line: treat as IDLE unless we can see a response bullet in the capture.
            if any(bullet_re.match(line) for line in lines):
                return TerminalStatus.COMPLETED
            return TerminalStatus.IDLE

        last_user = None
        for match in re.finditer(USER_PREFIX_PATTERN, clean_output, re.IGNORECASE | re.MULTILINE):
            last_user = match

        output_after_last_user = clean_output[last_user.start() :] if last_user else clean_output
        assistant_after_last_user = bool(
            last_user
            and re.search(
                ASSISTANT_PREFIX_PATTERN,
                output_after_last_user,
                re.IGNORECASE | re.MULTILINE,
            )
        )

        has_idle_prompt_at_end = bool(
            re.search(IDLE_PROMPT_AT_END_PATTERN, clean_output, re.IGNORECASE | re.MULTILINE)
        )

        # Only treat ERROR/WAITING prompts as actionable if they appear after the last user message
        # and are not part of an assistant response.
        if last_user is not None:
            if not assistant_after_last_user:
                if re.search(
                    WAITING_PROMPT_PATTERN,
                    output_after_last_user,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return TerminalStatus.WAITING_USER_ANSWER
                if re.search(
                    ERROR_PATTERN,
                    output_after_last_user,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return TerminalStatus.ERROR
        else:
            if re.search(WAITING_PROMPT_PATTERN, tail_output, re.IGNORECASE | re.MULTILINE):
                return TerminalStatus.WAITING_USER_ANSWER
            if re.search(ERROR_PATTERN, tail_output, re.IGNORECASE | re.MULTILINE):
                return TerminalStatus.ERROR
        if has_idle_prompt_at_end:
            # Consider COMPLETED only if we see an assistant marker after the last user message.
            if last_user is not None:
                if re.search(
                    ASSISTANT_PREFIX_PATTERN,
                    clean_output[last_user.start() :],
                    re.IGNORECASE | re.MULTILINE,
                ):
                    return TerminalStatus.COMPLETED

                return TerminalStatus.IDLE

            return TerminalStatus.IDLE

        # If we're not at an idle prompt and we don't see explicit errors/permission prompts,
        # assume the CLI is still producing output.
        return TerminalStatus.PROCESSING

    def get_idle_pattern_for_log(self) -> str:
        """Return Codex IDLE prompt pattern for log files."""
        return IDLE_PROMPT_PATTERN_LOG

    def extract_last_message_from_script(self, script_output: str) -> str:
        """Extract Codex's final response message using assistant label markers."""
        clean_output = re.sub(ANSI_CODE_PATTERN, "", script_output)

        matches = list(
            re.finditer(ASSISTANT_PREFIX_PATTERN, clean_output, re.IGNORECASE | re.MULTILINE)
        )

        if matches:
            last_match = matches[-1]
            start_pos = last_match.end()

            idle_after = re.search(
                IDLE_PROMPT_AT_END_PATTERN,
                clean_output[start_pos:],
                re.IGNORECASE | re.MULTILINE,
            )
            end_pos = start_pos + idle_after.start() if idle_after else len(clean_output)

            final_answer = clean_output[start_pos:end_pos].strip()

            if not final_answer:
                raise ValueError("Empty Codex response - no content found")

            return final_answer

        # Fallback: parse the newer Codex TUI transcript format (bulleted assistant lines).
        is_tui = bool(
            re.search(TUI_HEADER_PATTERN, clean_output, re.IGNORECASE)
            or re.search(TUI_STATUS_BAR_PATTERN, clean_output, re.IGNORECASE)
        )
        if not is_tui:
            raise ValueError("No Codex response found - no assistant marker detected")

        lines = clean_output.splitlines()
        prompt_re = re.compile(TUI_PROMPT_LINE_PATTERN, re.IGNORECASE)
        bullet_re = re.compile(TUI_RESPONSE_BULLET_PATTERN, re.IGNORECASE)
        interrupt_re = re.compile(TUI_INTERRUPT_MARKER_PATTERN, re.IGNORECASE)

        prompt_indices = [idx for idx, line in enumerate(lines) if prompt_re.match(line)]
        if not prompt_indices:
            raise ValueError("No Codex response found - no prompt line detected")

        # Find the last prompt that has at least one response bullet before the next prompt.
        last_prompt_with_bullets: Optional[int] = None
        next_prompt_for_last: Optional[int] = None
        for idx, prompt_idx in enumerate(prompt_indices):
            next_prompt_idx = (
                prompt_indices[idx + 1] if idx + 1 < len(prompt_indices) else len(lines)
            )
            if any(bullet_re.match(line) for line in lines[prompt_idx + 1 : next_prompt_idx]):
                last_prompt_with_bullets = prompt_idx
                next_prompt_for_last = next_prompt_idx

        if last_prompt_with_bullets is None or next_prompt_for_last is None:
            raise ValueError("No Codex response found - no response bullet detected")

        segment = lines[last_prompt_with_bullets + 1 : next_prompt_for_last]

        collected: list[str] = []
        for line in segment:
            if prompt_re.match(line):
                break
            if interrupt_re.search(line):
                break
            if bullet_re.match(line):
                collected.append(re.sub(r"^\s*•\s*", "", line))
                continue
            # Include wrapped/indented continuation lines if we're already collecting.
            if collected and line.strip():
                collected.append(line)

        final_answer = "\n".join(collected).strip()
        if not final_answer:
            raise ValueError("Empty Codex response - no content found")

        return final_answer

    def exit_cli(self) -> str:
        """Get the command to exit Codex CLI."""
        return "/exit"

    def cleanup(self) -> None:
        """Clean up Codex CLI provider."""
        self._initialized = False
