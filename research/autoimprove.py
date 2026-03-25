#!/usr/bin/env python3
"""ClawLite AutoImprove - Autonomous Agent Improvement System

Inspired by Karpathy's autoresearch. Analyzes conversations,
detects issues, generates tests, applies fixes, and tracks progress.

Usage:
    python research/autoimprove.py analyze   # Find issues in conversations
    python research/autoimprove.py test      # Run test suite
    python research/autoimprove.py fix       # Run fix loop
    python research/autoimprove.py report    # Generate progress report
    python research/autoimprove.py run       # Full cycle (for cron)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

import yaml

# Add research dir to path
RESEARCH_DIR = Path(__file__).parent
PROJECT_ROOT = RESEARCH_DIR.parent
sys.path.insert(0, str(RESEARCH_DIR))

from analyzer import load_conversations, analyze_conversations, Issue
from analyzer.llm_analyzer import analyze_with_llm, LLMAnalyzer
from tester import generate_test_case, TestCase, run_tests, load_test_cases, save_test_cases, run_tests_from_dir
from fixer import propose_fix, apply_fix, apply_fixes, FixProposal
from fixer.llm_proposer import propose_fix_with_llm, save_proposals_to_backlog

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('autoimprove')


def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    config_path = RESEARCH_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def get_workspace_path(config: Dict[str, Any]) -> str:
    """Get workspace path from config or default."""
    # Check config first, fallback to local workspace
    workspace = config.get('conversation', {}).get('workspace_path')
    if workspace and Path(workspace).exists():
        return workspace
    return str(PROJECT_ROOT / "workspace")


def update_progress(
    cycle: int,
    conversations_analyzed: int,
    issues_by_type: Dict[str, int],
    tests_created: int,
    fix_iterations: int,
    commits: List[str],
    metrics_before: Dict[str, float],
    metrics_after: Dict[str, float],
    pending_review: int,
) -> None:
    """Update progress.md with new cycle results."""
    progress_path = RESEARCH_DIR / "progress.md"
    
    # Read existing content
    content = progress_path.read_text()
    
    # Generate new entry
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M WIB')
    
    # Issue emoji mapping
    issue_emoji = {
        'loop_behavior': '🔄',
        'thinking_leak': '💭',
        'empty_response': '📭',
        'user_correction': '✋',
        'hallucination': '👻',
        'context_bloat': '📚',
        'slow_response': '🐢',
    }
    
    # Format issues
    issues_str = ""
    for issue_type, count in issues_by_type.items():
        emoji = issue_emoji.get(issue_type, '❓')
        issues_str += f"- {emoji} {issue_type}: {count} occurrences\n"
    
    # Format commits
    commits_str = "\n".join([f"- `{c}`" for c in commits]) if commits else "- None"
    
    # Format metrics delta
    metrics_rows = ""
    targets = {
        'loop_rate': 0,
        'thinking_leak_rate': 0,
        'error_rate': 2,
        'user_correction_rate': 5,
    }
    for metric in ['loop_rate', 'thinking_leak_rate', 'error_rate', 'user_correction_rate']:
        before = metrics_before.get(metric, 0)
        after = metrics_after.get(metric, 0)
        target = targets.get(metric, 0)
        
        if after <= target:
            status = "✓"
        elif after < before:
            status = "↓ improving"
        elif after > before:
            status = "↑ worsening"
        else:
            status = "—"
        
        metrics_rows += f"| {metric} | {before:.1f}% | {after:.1f}% | {target}% | {status} |\n"
    
    entry = f"""
## {timestamp}
**Cycle:** #{cycle}
**Conversations analyzed:** {conversations_analyzed}
**Issues detected:** {sum(issues_by_type.values())}
{issues_str}
**Tests created:** {tests_created}
**Fix iterations:** {fix_iterations}

**Commits:**
{commits_str}

**Metrics delta:**
| Metric | Before | After | Target | Status |
|--------|--------|-------|--------|--------|
{metrics_rows}
**Pending review:** {pending_review} items

---
"""
    
    # Insert after the header comment
    insert_marker = "<!-- New entries will be prepended below this line -->"
    if insert_marker in content:
        content = content.replace(insert_marker, insert_marker + entry)
    else:
        # Append to end
        content += entry
    
    progress_path.write_text(content)
    logger.info(f"Updated progress.md with cycle #{cycle}")


def update_metrics(metrics: Dict[str, float]) -> None:
    """Update metrics.json with current metrics."""
    metrics_path = RESEARCH_DIR / "metrics.json"
    
    data = json.loads(metrics_path.read_text())
    
    # Save current as history
    if data['current'].get('loop_rate') is not None:
        data['history'].append({
            'timestamp': datetime.now().isoformat(),
            'metrics': data['current'].copy(),
        })
    
    # Update current
    data['current'] = metrics
    data['last_updated'] = datetime.now().isoformat()
    
    # Set baseline if not set
    if data['baseline'].get('loop_rate') is None:
        data['baseline'] = metrics.copy()
    
    metrics_path.write_text(json.dumps(data, indent=2))
    logger.info("Updated metrics.json")


def add_to_backlog(idea: str, reason: str) -> None:
    """Add an improvement idea to the backlog."""
    backlog_path = RESEARCH_DIR / "ideas" / "backlog.md"
    
    content = backlog_path.read_text()
    
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M')
    
    entry = f"""
### {timestamp}
**Idea:** {idea}
**Reason:** {reason}
**Status:** ⏳ Awaiting approval

"""
    
    content += entry
    backlog_path.write_text(content)
    logger.info(f"Added idea to backlog: {idea}")


def load_processed_timestamps() -> Dict[str, str]:
    """Load dict of {convo_id: last_processed_timestamp_iso}."""
    metrics_path = RESEARCH_DIR / "metrics.json"
    if metrics_path.exists():
        data = json.loads(metrics_path.read_text())
        return data.get('last_processed', {}).get('timestamps', {})
    return {}


def save_processed_timestamps(new_timestamps: Dict[str, str]) -> None:
    """Save/merge processed timestamps per conversation.
    
    Args:
        new_timestamps: Dict of {convo_id: timestamp_iso} to merge
    """
    metrics_path = RESEARCH_DIR / "metrics.json"
    data = json.loads(metrics_path.read_text())
    
    # Merge with existing timestamps (newer wins)
    existing = data.get('last_processed', {}).get('timestamps', {})
    for convo_id, ts in new_timestamps.items():
        existing_ts = existing.get(convo_id)
        if not existing_ts or ts > existing_ts:
            existing[convo_id] = ts
    
    # Keep only last 30 days of conversations to prevent unbounded growth
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    existing = {k: v for k, v in existing.items() if k.split('_')[-1] >= cutoff}
    
    data['last_processed'] = {
        'timestamp': datetime.now().isoformat(),
        'timestamps': existing,
    }
    metrics_path.write_text(json.dumps(data, indent=2))
    logger.info(f"Saved timestamps for {len(new_timestamps)} conversations")


def cmd_analyze(args) -> Dict[str, Any]:
    """Analyze conversations and detect issues."""
    config = load_config()
    workspace_path = get_workspace_path(config)
    
    lookback_hours = config.get('conversation', {}).get('lookback_hours', 24)
    min_exchanges = config.get('conversation', {}).get('min_exchanges', 2)
    
    # Load already processed timestamps
    processed_timestamps = load_processed_timestamps()
    logger.info(f"Tracking {len(processed_timestamps)} conversation timestamps")
    
    logger.info(f"Analyzing conversations from last {lookback_hours} hours")
    
    # Load conversations (skip already processed exchanges)
    since = datetime.now() - timedelta(hours=lookback_hours)
    conversations, new_timestamps = load_conversations(
        workspace_path, 
        since=since, 
        min_exchanges=min_exchanges,
        processed_timestamps=processed_timestamps,
    )
    
    if not conversations:
        logger.info("No new conversations to analyze")
        return {'conversations': 0, 'issues': 0, 'new_timestamps': {}}
    
    # Pattern-based analysis (fast, known issues)
    results = analyze_conversations(conversations)
    results['new_timestamps'] = new_timestamps
    
    # LLM-powered analysis (discovers new issues)
    llm_config = config.get('llm_analysis', {})
    if llm_config.get('enabled', False):
        logger.info("Running LLM-powered analysis to discover new issue types...")
        try:
            llm_issues = analyze_with_llm(conversations, config)
            
            # Merge LLM-discovered issues (avoid duplicates)
            existing_descriptions = {i.description for i in results['issues']}
            new_llm_issues = []
            for issue in llm_issues:
                if issue.description not in existing_descriptions:
                    new_llm_issues.append(issue)
                    results['issues'].append(issue)
                    results['issues_by_type'][issue.type] = results['issues_by_type'].get(issue.type, 0) + 1
            
            results['total_issues'] = len(results['issues'])
            results['llm_discovered'] = len(new_llm_issues)
            
            if new_llm_issues:
                logger.info(f"LLM discovered {len(new_llm_issues)} additional issues")
                for issue in new_llm_issues:
                    if issue.context.get('is_new_type'):
                        logger.info(f"  🆕 New issue type: {issue.type}")
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}")
            results['llm_discovered'] = 0
    
    logger.info(f"Found {results['total_issues']} issues in {results['conversations_analyzed']} NEW conversations")
    
    for issue_type, count in results['issues_by_type'].items():
        logger.info(f"  - {issue_type}: {count}")
    
    return results


def cmd_test(args) -> Dict[str, Any]:
    """Run test suite."""
    config = load_config()
    workspace_path = get_workspace_path(config)
    cases_dir = str(RESEARCH_DIR / "tester" / "cases")
    
    logger.info("Running test suite")
    
    results = run_tests_from_dir(
        cases_dir=cases_dir,
        config=config,
        workspace_path=workspace_path,
        filter_type=args.type if hasattr(args, 'type') else None,
    )
    
    logger.info(f"Tests: {results['passed']}/{results['total']} passed ({results['pass_rate']:.1f}%)")
    
    return results


def cmd_fix(args) -> Dict[str, Any]:
    """Run fix loop."""
    config = load_config()
    workspace_path = get_workspace_path(config)
    cases_dir = str(RESEARCH_DIR / "tester" / "cases")
    
    max_iterations = config.get('testing', {}).get('max_iterations', 10)
    auto_commit = config.get('git', {}).get('auto_commit', True)
    commit_prefix = config.get('git', {}).get('commit_prefix', 'autoimprove:')
    
    logger.info(f"Starting fix loop (max {max_iterations} iterations)")
    
    # Load test cases
    test_cases = load_test_cases(cases_dir)
    test_cases_dict = {tc.id: tc for tc in test_cases}
    
    if not test_cases:
        logger.info("No test cases found")
        return {'iterations': 0, 'fixed': 0}
    
    commits = []
    iterations = 0
    
    for i in range(max_iterations):
        iterations = i + 1
        logger.info(f"Fix iteration {iterations}/{max_iterations}")
        
        # Run tests
        results = run_tests(test_cases, config, workspace_path)
        
        if results['failed'] == 0:
            logger.info("All tests passing!")
            break
        
        # Get failing results
        failing = [r for r in results['results'] if not r.passed]
        
        # Propose fixes
        proposals = []
        for result in failing:
            tc = test_cases_dict.get(result.test_id)
            if tc:
                proposal = propose_fix(result, tc, str(PROJECT_ROOT))
                if proposal:
                    proposals.append(proposal)
        
        if not proposals:
            logger.info("No fixes can be proposed")
            break
        
        # Apply fixes
        fix_results = apply_fixes(
            proposals,
            str(PROJECT_ROOT),
            auto_commit=auto_commit,
            commit_prefix=commit_prefix,
        )
        
        for r in fix_results['results']:
            if r.get('committed'):
                commits.append(r.get('commit_hash', 'unknown'))
        
        if fix_results['applied'] == 0:
            logger.info("No fixes applied, stopping")
            break
    
    return {
        'iterations': iterations,
        'commits': commits,
    }


def cmd_report(args) -> None:
    """Generate progress report."""
    config = load_config()
    
    # Load metrics
    metrics_path = RESEARCH_DIR / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    
    print("\n" + "=" * 50)
    print("ClawLite AutoImprove Report")
    print("=" * 50)
    
    print(f"\nLast updated: {metrics.get('last_updated', 'Never')}")
    
    print("\nCurrent Metrics:")
    current = metrics.get('current', {})
    targets = metrics.get('targets', {})
    
    for metric, value in current.items():
        if value is not None:
            target = targets.get(metric, 'N/A')
            status = "✓" if value <= target else "✗"
            print(f"  {metric}: {value:.1f}% (target: {target}%) {status}")
    
    print("\nBaseline Metrics:")
    baseline = metrics.get('baseline', {})
    for metric, value in baseline.items():
        if value is not None:
            print(f"  {metric}: {value:.1f}%")
    
    print("\n" + "=" * 50)


def cmd_run(args) -> None:
    """Run analysis cycle (for cron) — NO auto-fix, Aisyah reviews.
    
    This generates a report for Aisyah to review. Fixes are only
    applied when Aisyah explicitly runs the fix command.
    """
    logger.info("Starting AutoImprove analysis cycle (Aisyah will review)")
    
    config = load_config()
    
    # 1. Analyze conversations
    analysis = cmd_analyze(args)
    
    conversations_count = analysis.get('conversations_analyzed', 0)
    issues_count = analysis.get('total_issues', 0)
    
    if conversations_count == 0:
        logger.info("No new conversations to analyze")
        return
    
    # Save processed timestamps so we don't re-process same exchanges
    new_timestamps = analysis.get('new_timestamps', {})
    if new_timestamps:
        save_processed_timestamps(new_timestamps)
    
    if issues_count == 0:
        logger.info("No issues found - ClawLite is performing well!")
        # Still update progress to track
        update_analysis_report(
            conversations_analyzed=conversations_count,
            issues_by_type={},
            metrics=analysis.get('metrics', {}),
            proposals=[],
        )
        return
    
    # 2. Generate fix proposals (but don't apply!)
    issues = analysis.get('issues', [])
    proposals = []
    llm_proposals = []
    
    # Check if LLM proposer is enabled
    use_llm_proposer = config.get('llm_analysis', {}).get('enabled', False)
    
    for issue in issues:
        # Create a fake result/test_case to propose a fix
        fake_result = type('FakeResult', (), {
            'passed': False,
            'test_id': f'issue_{issue.type}',
            'response': issue.exchange.assistant_response,
            'tool_calls': [],
            'duration_ms': 0,
        })()
        fake_tc = type('FakeTC', (), {
            'id': f'issue_{issue.type}',
            'issue_type': issue.type,
            'user_message': issue.exchange.user_message,
        })()
        
        # Try built-in proposer first
        proposal = propose_fix(fake_result, fake_tc, str(PROJECT_ROOT))
        if proposal:
            proposals.append(proposal)
            add_to_backlog(
                idea=proposal.description,
                reason=f"Issue type: {issue.type}, File: {proposal.file_path}",
            )
        elif use_llm_proposer:
            # Fallback to LLM proposer for unknown issue types
            llm_proposal = propose_fix_with_llm(issue, config)
            if llm_proposal:
                llm_proposals.append(llm_proposal)
                add_to_backlog(
                    idea=f"[LLM] {llm_proposal.description}",
                    reason=f"Issue type: {issue.type}, File: {llm_proposal.target_file}, Risk: {llm_proposal.risk_level}",
                )
    
    # Save LLM proposals to backlog with details
    if llm_proposals:
        save_proposals_to_backlog(llm_proposals, RESEARCH_DIR / "ideas" / "llm_proposals.md")
        logger.info(f"Generated {len(llm_proposals)} LLM fix proposals")
    
    # 3. Update progress with analysis results (no fixes applied)
    update_analysis_report(
        conversations_analyzed=conversations_count,
        issues_by_type=analysis.get('issues_by_type', {}),
        metrics=analysis.get('metrics', {}),
        proposals=proposals,
    )
    
    # 4. Notify Aisyah (via file that she can check)
    notify_path = RESEARCH_DIR / "REVIEW_NEEDED.md"
    notify_path.write_text(f"""# AutoImprove Analysis Ready for Review

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M WIB')}

## Summary
- **Conversations analyzed:** {conversations_count}
- **Issues detected:** {issues_count}
- **Fix proposals:** {len(proposals)}

## Issues by Type
{chr(10).join([f"- {t}: {c}" for t, c in analysis.get('issues_by_type', {}).items()])}

## Action Required
Aisyah, please review:
1. Check `research/progress.md` for details
2. Review proposals in `research/ideas/backlog.md`
3. Run `python research/autoimprove.py fix` to apply approved fixes

---
*Delete this file after review*
""")
    
    logger.info(f"Analysis complete: {issues_count} issues found, {len(proposals)} fix proposals")
    logger.info("Created REVIEW_NEEDED.md for Aisyah to review")


def update_analysis_report(
    conversations_analyzed: int,
    issues_by_type: Dict[str, int],
    metrics: Dict[str, float],
    proposals: List[Any],
) -> None:
    """Update progress.md with analysis results (no fixes)."""
    progress_path = RESEARCH_DIR / "progress.md"
    
    # Read existing content
    content = progress_path.read_text()
    
    # Count cycles
    cycle = content.count("**Cycle:**") + 1
    
    # Generate new entry
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M WIB')
    
    # Issue emoji mapping
    issue_emoji = {
        'loop_behavior': '🔄',
        'thinking_leak': '💭',
        'empty_response': '📭',
        'user_correction': '✋',
        'hallucination': '👻',
        'context_bloat': '📚',
        'slow_response': '🐢',
    }
    
    # Format issues
    issues_str = ""
    for issue_type, count in issues_by_type.items():
        emoji = issue_emoji.get(issue_type, '❓')
        issues_str += f"- {emoji} {issue_type}: {count}\n"
    
    if not issues_str:
        issues_str = "- ✅ No issues detected\n"
    
    # Format metrics
    metrics_rows = ""
    for metric, value in metrics.items():
        if value is not None:
            metrics_rows += f"| {metric} | {value:.1f}% |\n"
    
    entry = f"""
## {timestamp}
**Cycle:** #{cycle} — Analysis Only (Awaiting Aisyah Review)
**Conversations analyzed:** {conversations_analyzed}
**Issues detected:** {sum(issues_by_type.values())}
{issues_str}
**Fix proposals generated:** {len(proposals)}
**Status:** ⏳ Awaiting Aisyah's review

**Current Metrics:**
| Metric | Value |
|--------|-------|
{metrics_rows}
---
"""
    
    # Insert after the header comment
    insert_marker = "<!-- New entries will be prepended below this line -->"
    if insert_marker in content:
        content = content.replace(insert_marker, insert_marker + entry)
    else:
        content += entry
    
    progress_path.write_text(content)
    logger.info(f"Updated progress.md with cycle #{cycle}")


def main():
    parser = argparse.ArgumentParser(
        description='ClawLite AutoImprove - Autonomous Agent Improvement System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze conversations for issues')
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # test command
    test_parser = subparsers.add_parser('test', help='Run test suite')
    test_parser.add_argument('--type', help='Only run tests of this issue type')
    test_parser.set_defaults(func=cmd_test)
    
    # fix command
    fix_parser = subparsers.add_parser('fix', help='Run fix loop')
    fix_parser.set_defaults(func=cmd_fix)
    
    # report command
    report_parser = subparsers.add_parser('report', help='Generate progress report')
    report_parser.set_defaults(func=cmd_report)
    
    # run command (full cycle)
    run_parser = subparsers.add_parser('run', help='Run full improvement cycle')
    run_parser.set_defaults(func=cmd_run)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
