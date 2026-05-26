from __future__ import annotations

BASH_COMPLETION = r"""# bash completion for portmanager
_portmanager()
{
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="init scan claim release rename-service move-project adopt sync doctor run roots guardrails"

    case "$prev" in
        portmanager)
            COMPREPLY=( $(compgen -W "$commands --registry --version --help" -- "$cur") )
            return 0
            ;;
        roots)
            COMPREPLY=( $(compgen -W "add list" -- "$cur") )
            return 0
            ;;
        guardrails)
            COMPREPLY=( $(compgen -W "install" -- "$cur") )
            return 0
            ;;
        --kind)
            COMPREPLY=( $(compgen -W "web api db redis worker other" -- "$cur") )
            return 0
            ;;
    esac

    COMPREPLY=( $(compgen -W "--help --json --all --dry-run --force --kind --port --source-file --bind-host --notes --root --range-start --range-end" -- "$cur") )
    return 0
}
complete -F _portmanager portmanager
"""

ZSH_COMPLETION = r"""#compdef portmanager
_portmanager() {
  local -a commands
  commands=(
    'init:Create a registry in this workspace'
    'scan:Scan configured projects for port bindings'
    'claim:Claim a stable managed port'
    'release:Retire a service assignment'
    'rename-service:Rename a project service'
    'move-project:Move registry entries to a new path'
    'adopt:Register discovered existing bindings'
    'sync:Generate per-project env files'
    'doctor:Validate registry state'
    'run:Run a command with managed env'
    'roots:Manage discovery roots'
    'guardrails:Install agent guardrails'
  )

  _arguments -C \
    '--registry[Path to ports.toml]:registry:_files' \
    '--version[Show version]' \
    '1:command:->command' \
    '*::arg:->args'

  case $state in
    command)
      _describe 'commands' commands
      ;;
    args)
      case $words[2] in
        roots)
          _arguments '1:roots command:(add list)' '*:path:_files'
          ;;
        guardrails)
          _arguments '1:guardrails command:(install)' '--dry-run[Preview targets]'
          ;;
        claim)
          _arguments '--kind[Service kind]:(web api db redis worker other)' '--port[Port]' '--dry-run[Preview claim]' '*:path:_files'
          ;;
        doctor|scan|adopt|sync|release|rename-service|move-project|init)
          _arguments '--json[JSON output]' '--all[All projects]' '--dry-run[Preview changes]' '--force[Overwrite existing registry]' '*:path:_files'
          ;;
      esac
      ;;
  esac
}
_portmanager "$@"
"""


def completion_script(shell: str) -> str:
    if shell == "bash":
        return BASH_COMPLETION
    if shell == "zsh":
        return ZSH_COMPLETION
    raise ValueError(f"unsupported shell: {shell}")

