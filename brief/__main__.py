"""Command line entry point: python -m brief <command> ..."""
import argparse
import json
import sys

from .util import kyiv_date, now_utc


def cmd_collect(a):
    from . import collect

    report = collect.run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Partial feed failures are logged in the pool; only a total failure fails the job.
    if report["sources_attempted"] and len(report["errors"]) >= report["sources_attempted"]:
        sys.exit("all sources failed")


def cmd_registry(a):
    from . import registry

    today = kyiv_date(now_utc())
    media = registry.sync_map() if not a.skip_sync else registry.load_json(registry.REGISTRY)["media"]
    if not a.skip_feeds:
        registry.discover_feeds(media, today, only_missing=a.only_missing)
    registry.save(media, today)
    active = sum(1 for m in media if m.get("feed_status") == "active")
    print(f"{len(media)} outlets on the map; {active} with a verified public feed")


def cmd_draft(a):
    from . import edition

    date = a.date or kyiv_date(now_utc())
    path, draft = edition.build_and_save(date)
    s = draft["stats"]
    print(f"{path}\n{s['stories']} stories, {s['sentences']} sentences, "
          f"{s['needs_review']} need editor confirmation, {s['excluded']} excluded")


def cmd_check(a):
    from . import review

    result = review.check_draft(a.date)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    for p in result["problems"]:
        print("-", p)
    sys.exit(1 if result["problems"] else 0)


def cmd_approve(a):
    from . import review

    approved = review.approve(a.date, a.reviewer, expected_hash=a.expected_hash)
    print(f"approved by {approved['approved_by']}; script sha256 {approved['script_sha256']}")


def cmd_render(a):
    from . import render

    manifest = render.render(a.date, provider_name=a.provider, voice=a.voice)
    keys = ("provider", "voice", "duration_sec", "characters", "estimated_cost_usd", "api_calls", "cached_chunks",
            "elapsed_sec")
    print(json.dumps({k: manifest[k] for k in keys}, indent=2))


def cmd_verify(a):
    from . import verify

    asr = verify.verify(a.date, model_size=a.model, threshold=a.threshold, model_dir=a.model_dir)
    print(json.dumps({k: asr[k] for k in ("model", "mean_cer", "failed")}, ensure_ascii=False, indent=2))


def cmd_publish(a):
    from . import publish

    path = publish.publish(a.date, allow_mock=a.allow_mock)
    print(path)


def cmd_prune(a):
    from . import prune

    removed = prune.prune(keep_days=a.keep_days)
    print(f"removed {len(removed)} edition(s): {', '.join(removed) or '—'}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="brief")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("collect", help="fetch feeds into data/raw").set_defaults(fn=cmd_collect)

    r = sub.add_parser("registry", help="refresh config/media_map.json from the official map")
    r.add_argument("--skip-sync", action="store_true")
    r.add_argument("--skip-feeds", action="store_true")
    r.add_argument("--only-missing", action="store_true")
    r.set_defaults(fn=cmd_registry)

    d = sub.add_parser("draft", help="build editions/<date>/draft.json")
    d.add_argument("--date")
    d.set_defaults(fn=cmd_draft)

    c = sub.add_parser("check", help="re-run fact checks on the (edited) draft")
    c.add_argument("--date", required=True)
    c.set_defaults(fn=cmd_check)

    ap = sub.add_parser("approve", help="record editorial approval of the draft")
    ap.add_argument("--date", required=True)
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--expected-hash", help="sha256 shown on the review page; guards against approving a changed text")
    ap.set_defaults(fn=cmd_approve)

    rn = sub.add_parser("render", help="synthesize the approved script")
    rn.add_argument("--date", required=True)
    rn.add_argument("--provider", default="mock")
    rn.add_argument("--voice")
    rn.set_defaults(fn=cmd_render)

    v = sub.add_parser("verify-audio", help="optional: transcribe rendered audio and compare with the script")
    v.add_argument("--date", required=True)
    v.add_argument("--model", default="small")
    v.add_argument("--model-dir")
    v.add_argument("--threshold", type=float, default=0.20)
    v.set_defaults(fn=cmd_verify)

    pb = sub.add_parser("publish", help="publish an approved and fully rendered edition")
    pb.add_argument("--date", required=True)
    pb.add_argument("--allow-mock", action="store_true", help="local testing only")
    pb.set_defaults(fn=cmd_publish)

    pr = sub.add_parser("prune", help="delete editions (audio, text, drafts) older than N days")
    pr.add_argument("--keep-days", type=int, default=7)
    pr.set_defaults(fn=cmd_prune)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
