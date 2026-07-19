"""Command-line interface.

Key handling (read this): the API key is *only* ever read from an environment
variable named by --api-key-env (default OPENAI_API_KEY, or ANTHROPIC_API_KEY for
the anthropic protocol). There is deliberately no --key flag, so your key cannot
end up in shell history, argv, or a saved command. The key is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .client import Endpoint
from . import probes as probes_pkg
from .probes import ProbeContext
from . import report
from . import card as card_mod
from . import families

_CARD_TEXT_FORMATS = ("txt", "md", "svg", "html")
_CARD_FORMATS = _CARD_TEXT_FORMATS + ("png", "all")


def _default_key_env(protocol: str) -> str:
    return "ANTHROPIC_API_KEY" if protocol == "anthropic" else "OPENAI_API_KEY"


def _load_reference(path: Optional[str]) -> Dict[str, Any]:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "data", "tokenizers.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _read_key(env_name: str, label: str) -> Optional[str]:
    key = os.environ.get(env_name)
    if not key:
        sys.stderr.write(
            "warning: no key found in $%s for the %s endpoint; sending "
            "unauthenticated (most hosted endpoints will 401).\n" % (env_name, label))
    return key


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llm-honesty-probe",
        description="Heuristic signals about whether an OpenAI-/Anthropic-compatible "
                    "endpoint serves the model it claims. Signals, not proof.")
    p.add_argument("--version", action="version", version="llm-honesty-probe %s" % __version__)
    p.add_argument("--base-url", help="Endpoint base URL, e.g. https://host/v1")
    p.add_argument("--claimed-model", help="The model id the endpoint claims / you pay for")
    p.add_argument("--protocol", choices=["openai", "anthropic"], default="openai")
    p.add_argument("--api-key-env", default=None,
                   help="Name of the env var holding the API key (default OPENAI_API_KEY / "
                        "ANTHROPIC_API_KEY). The key is read from the environment only.")
    # Optional reference endpoint for differential signals.
    p.add_argument("--compare-base-url", default=None,
                   help="A second endpoint (e.g. the official API) to diff against")
    p.add_argument("--compare-model", default=None)
    p.add_argument("--compare-protocol", choices=["openai", "anthropic"], default="openai")
    p.add_argument("--compare-api-key-env", default=None)
    # Probe selection / tuning.
    p.add_argument("--probes", default="all",
                   help="Comma list: %s or 'all'" % ",".join(sorted(_all_probe_names())))
    p.add_argument("--repeats", type=int, default=5, help="Repeats for the consistency probe")
    p.add_argument("--max-tokens", type=int, default=64)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--needle-lengths", default="2000,8000,24000",
                   help="Comma list of approx context sizes (chars) for the needle probe")
    p.add_argument("--reference", default=None, help="Path to a tokenizer reference JSON")
    p.add_argument("--config", default=None, help="Path to a JSON config with overrides")
    # Output.
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    p.add_argument("--out", default=None, help="Write output to a file instead of stdout")
    p.add_argument("--list-probes", action="store_true", help="List probes and exit")
    p.add_argument("--self-test", action="store_true",
                   help="Run against a built-in mock endpoint (no credentials needed)")
    # Verdict card: a share-friendly PASS / SUSPICIOUS summary of the run.
    p.add_argument("--card", action="store_true",
                   help="Render a share-friendly verdict card instead of the full report")
    p.add_argument("--card-format", choices=list(_CARD_FORMATS), default="txt",
                   help="Card format: txt (default), md, svg, html, png, or 'all' "
                        "(writes every format; requires --card-out as a directory)")
    p.add_argument("--card-out", default=None,
                   help="Write the card here (a file, or a directory when --card-format=all). "
                        "Text/md/svg/html print to stdout if omitted; png requires this.")
    p.add_argument("--card-show-endpoint", action="store_true",
                   help="Include the tested endpoint host on the card (masked by default so "
                        "a shared card doesn't out the provider you tested)")
    return p


def _all_probe_names() -> List[str]:
    probes_pkg.load_builtin()
    return probes_pkg.available()


def _select_probes(spec: str) -> List[str]:
    probes_pkg.load_builtin()
    available = probes_pkg.available()
    if spec.strip() == "all":
        return available
    chosen = []
    for name in spec.split(","):
        name = name.strip()
        if not name:
            continue
        if name not in available:
            raise SystemExit("unknown probe %r (available: %s)" % (name, ", ".join(available)))
        chosen.append(name)
    return chosen


def _run(base_url: str, protocol: str, api_key: Optional[str], model: str,
         probe_names: List[str], ctx: ProbeContext, timeout: float):
    endpoint = Endpoint(base_url=base_url, protocol=protocol, api_key=api_key,
                        timeout=timeout, label="primary")
    signals = []
    for name in probe_names:
        fn = probes_pkg.get(name)
        if fn is None:
            continue
        try:
            signals.extend(fn(endpoint, ctx))
        except Exception as exc:  # noqa: BLE001 - a probe must never crash the run
            from .signals import inconclusive
            from .redaction import redact
            signals.append(inconclusive(name, name, "probe crashed: %s" % redact(str(exc))))
    return signals


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_probes:
        probes_pkg.load_builtin()
        for name in probes_pkg.available():
            print("%-12s %s" % (name, probes_pkg.description(name)))
        return 0

    # Resolve config.
    user_config: Dict[str, Any] = {}
    if args.config:
        try:
            with open(args.config, "r", encoding="utf-8") as fh:
                user_config = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("could not read --config: %s" % exc)

    needle_lengths = [int(x) for x in str(args.needle_lengths).split(",") if x.strip()]
    reference = _load_reference(args.reference)

    # Self-test mode: stand up the mock and point everything at it.
    if args.self_test:
        # With --card we generate two sample cards: an honest run (PASS) and a
        # deliberately degraded run (SUSPICIOUS), so people can see both states.
        if args.card:
            honest_sigs, honest_meta = _run_selftest(False, args, reference, needle_lengths)
            degraded_sigs, degraded_meta = _run_selftest(True, args, reference, needle_lengths)
            _emit_cards([("honest", honest_sigs, honest_meta),
                         ("degraded", degraded_sigs, degraded_meta)], args)
            return 0
        signals, meta = _run_selftest(bool(user_config.get("degrade")), args,
                                      reference, needle_lengths)
        _emit(signals, meta, args)
        return 0

    # Normal mode requires a target.
    if not args.base_url or not args.claimed_model:
        raise SystemExit("error: --base-url and --claimed-model are required "
                         "(or use --self-test / --list-probes).")

    key_env = args.api_key_env or _default_key_env(args.protocol)
    api_key = _read_key(key_env, "primary")

    compare_endpoint = None
    compare_model = None
    mode = "single-endpoint"
    if args.compare_base_url:
        cmp_key_env = args.compare_api_key_env or _default_key_env(args.compare_protocol)
        cmp_key = _read_key(cmp_key_env, "reference")
        compare_endpoint = Endpoint(base_url=args.compare_base_url, protocol=args.compare_protocol,
                                    api_key=cmp_key, timeout=args.timeout, label="reference")
        compare_model = args.compare_model or args.claimed_model
        mode = "compare (vs reference endpoint)"

    ctx = ProbeContext(
        claimed_model=args.claimed_model, repeats=args.repeats, max_tokens=args.max_tokens,
        compare_endpoint=compare_endpoint, compare_model=compare_model,
        tokenizer_reference=reference, needle_lengths=needle_lengths, config=user_config)

    probe_names = _select_probes(args.probes)
    signals = _run(args.base_url, args.protocol, api_key, args.claimed_model,
                   probe_names, ctx, args.timeout)
    meta = _meta(args.base_url, args.protocol, args.claimed_model,
                 args.compare_base_url, args.compare_protocol, compare_model, mode, probe_names)
    if args.card:
        _emit_cards([("card", signals, meta)], args)
    else:
        _emit(signals, meta, args)
    return 0


def _run_selftest(degrade, args, reference, needle_lengths):
    """Run the probe suite against the built-in mock and return (signals, meta)."""
    from ._mockserver import running_server
    key = "sk-selftest-not-a-real-key"
    os.environ.setdefault("LLM_PROBE_SELFTEST_KEY", key)
    with running_server(degrade=degrade) as base_url:
        ctx = ProbeContext(
            claimed_model=args.claimed_model or "gpt-4o",
            repeats=args.repeats, max_tokens=args.max_tokens,
            tokenizer_reference=reference, needle_lengths=needle_lengths,
            config={"degrade": degrade})
        probe_names = _select_probes(args.probes)
        signals = _run(base_url, "openai", key, ctx.claimed_model, probe_names, ctx, args.timeout)
        mode = "self-test (mock endpoint, %s)" % ("degraded" if degrade else "honest")
        meta = _meta(base_url, "openai", ctx.claimed_model, None, None, None, mode, probe_names)
    return signals, meta


def _meta(base_url, protocol, claimed_model, cmp_url, cmp_protocol, cmp_model, mode, probe_names):
    meta = {
        "base_url": base_url, "protocol": protocol, "claimed_model": claimed_model,
        "mode": mode, "probes": probe_names,
        "model_family": families.tokenizer_family(claimed_model),
    }
    if cmp_url:
        meta.update({"compare_base_url": cmp_url, "compare_protocol": cmp_protocol,
                     "compare_model": cmp_model})
    return meta


def _emit(signals, meta, args) -> None:
    text = report.render_json(signals, meta) if args.json else report.render_text(signals, meta)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)


def _write_png(card, path) -> str:
    """Write a PNG for *card* to *path*; fall back to an SVG if no rasterizer."""
    svg = card_mod.render_svg(card)
    ok, note = card_mod.to_png(svg, path)
    if ok:
        sys.stderr.write("wrote %s (%s)\n" % (path, note))
        return path
    alt = os.path.splitext(path)[0] + ".svg"
    with open(alt, "w", encoding="utf-8") as fh:
        fh.write(svg)
    sys.stderr.write("note: %s -> wrote %s instead\n" % (note, alt))
    return alt


def _write_card(card, fmt, path) -> None:
    if fmt == "png":
        _write_png(card, path)
        return
    text = card_mod.render(card, fmt)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    sys.stderr.write("wrote %s\n" % path)


def _emit_cards(entries, args) -> None:
    """Render one or more verdict cards. *entries* is a list of (name, signals, meta)."""
    fmt = args.card_format
    cards = [(name, card_mod.build_card(sigs, meta, show_endpoint=args.card_show_endpoint))
             for name, sigs, meta in entries]

    if fmt == "all":
        if not args.card_out:
            raise SystemExit("error: --card-format all requires --card-out <directory>")
        os.makedirs(args.card_out, exist_ok=True)
        count = 0
        for name, card in cards:
            for f in _CARD_TEXT_FORMATS:
                _write_card(card, f, os.path.join(args.card_out, "%s.%s" % (name, f)))
                count += 1
            _write_png(card, os.path.join(args.card_out, "%s.png" % name))
            count += 1
        sys.stderr.write("done: %d card file(s) in %s\n" % (count, args.card_out))
        return

    if args.card_out:
        if len(cards) > 1:
            base, ext = os.path.splitext(args.card_out)
            ext = ext or ("." + fmt)
            for name, card in cards:
                _write_card(card, fmt, "%s-%s%s" % (base, name, ext))
        else:
            _write_card(cards[0][1], fmt, args.card_out)
        return

    # stdout (text formats only).
    if fmt == "png":
        raise SystemExit("error: --card-format png needs --card-out <file.png>")
    chunks = []
    for name, card in cards:
        if len(cards) > 1:
            chunks.append("===== %s =====" % name)
        chunks.append(card_mod.render(card, fmt))
    print("\n\n".join(chunks))


if __name__ == "__main__":
    raise SystemExit(main())
