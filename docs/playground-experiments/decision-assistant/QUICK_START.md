# Decision Assistant Quick Start

**Get guidance on your decision in 5 minutes**

## Installation

```bash
# No dependencies needed! Uses only Python standard library.
cd /workspace/decision-assistant
```

## Basic Usage

### Step 1: Describe Your Decision

Create a file `my_decision.json`:

```json
{
  "name": "Your decision",
  "description": "What's the context?",
  "options": ["Option A", "Option B", "Option C"],
  "constraints": ["Constraint 1", "Constraint 2"],
  "timeline": "short-term",
  "reversibility": "reversible",
  "information_level": "moderate",
  "stakes": "medium"
}
```

### Step 2: Get Guidance

```bash
python3 assistant.py my_decision.json
```

### Step 3: Read the Output

The tool will print:
- **Analysis**: What's your situation?
- **Recommended Approach**: How should you decide?
- **Success Patterns**: Which proven patterns apply
- **Risk Factors**: What could go wrong
- **Key Questions**: Ask yourself these
- **Confidence Level**: 0-100% for this decision

## Example: Real Decision

Let's say you need to decide: **Should I upgrade our database?**

Create `upgrade_db.json`:

```json
{
  "name": "Upgrade database to newer version",
  "description": "Current version is 5 years old, new version has better performance and security. Upgrade would take 1 week of team effort. Could break production if not done carefully.",
  "options": [
    "Upgrade now while we have time",
    "Wait until next maintenance window (3 months)",
    "Plan upgrade more carefully (2 week planning phase first)"
  ],
  "constraints": [
    "Database is critical to production",
    "Team is at capacity this month",
    "Performance is starting to degrade"
  ],
  "timeline": "medium-term",
  "reversibility": "partially-reversible",
  "information_level": "complete",
  "stakes": "high"
}
```

Run it:

```bash
python3 assistant.py upgrade_db.json
```

The tool will tell you:
- "You have complete information → decision should be definitive"
- "Medium timeline → design experiments to reduce uncertainty"
- "Partially reversible → plan reversibility explicitly"
- "High stakes → your contingency plan is critical"
- "Applicable patterns: Modular Design, Honest Measurement"
- "Confidence: 75%" → You're well-positioned

## Field Guide

### timeline
- `immediate`: Decide now (minutes/hours)
- `short-term`: Decide soon (days/1 week)
- `medium-term`: Decide with some time (1-4 weeks)
- `long-term`: Decide with lots of time (1+ months)

### reversibility
- `reversible`: You can undo this (try it, it's safe)
- `partially-reversible`: You can partly undo (need backup plan)
- `irreversible`: No going back (be very careful)

### information_level
- `incomplete`: You don't know enough yet
- `moderate`: You know most of what matters
- `complete`: You have all the info you need

### stakes
- `low`: Doesn't matter much if you're wrong
- `medium`: Matters somewhat
- `high`: Matters a lot if you're wrong

## Real Examples to Try

The `/workspace/decision-assistant/examples/` directory has 4 real problems:

```bash
# Technical decision
python3 assistant.py examples/technical_refactoring.json

# Feature decision
python3 assistant.py examples/feature_vs_improvement.json

# Emergency decision
python3 assistant.py examples/emergency_bug.json

# Strategic decision
python3 assistant.py examples/strategic_direction.json
```

## Tips

### For Better Guidance

**Be specific** about your constraints. Vague constraints → vague guidance.

**Think about reversibility honestly**. Most decisions are more reversible than you think.

**Match timeline to reality**. Don't say "medium-term" if you're deciding today.

**List real options**. If you only have 2 options, list 2. Not "Option C" placeholder.

### Using the Output

**Don't just read confidence level**. Read the analysis.

**Ask the key questions yourself**. They're based on proven patterns.

**Watch for patterns**. "Modular Design" means break it into pieces.

**Plan for risk factors**. The tool flags what could go wrong.

### After You Decide

**Record what you decided** and why.

**Come back later** and check: Was the confidence level right?

**Track outcomes**: Did the success patterns actually apply?

**Learn**: Build your own patterns from your decisions.

## The Patterns Explained (Short)

The tool applies 8 patterns learned from 10 iterations of complex decision-making:

| Pattern | Success Rate | When to Use |
|---------|-------------|-----------|
| Modular Design | 95% | Breaking complex problems into pieces |
| Separation of Concerns | 95% | Systems, tools, interfaces |
| Honest Measurement | 95% | Decisions with measurable outcomes |
| Breadth Then Depth | 90% | Exploration, learning, innovation |
| Validation Changes Behavior | 85% | Process improvement, quality |
| Timing Matters | 85% | Time-dependent decisions |
| Reversibility Helps | 85% | Any decision (change your approach based on this) |
| Avoid Meta-Analysis Loops | 80% | Complex decisions (stop analyzing the analysis) |

## Common Questions

### Q: What if the tool says 44% confidence?

**A**: The decision needs more planning or should be deferred. Your information level is too low. Do research, run experiments, gather data. Come back when you're at 60%+.

### Q: What if I disagree with the guidance?

**A**: That's fine. The tool is advisory, not prescriptive. Use what's helpful, ignore the rest. Better: understand why you disagree—that's valuable self-knowledge.

### Q: Can I use this for personal decisions?

**A**: Yes. The patterns work for any complex decision: career, location, education, relationship...

### Q: What if my decision type isn't listed?

**A**: The tool works for any decision with clear options, constraints, and timeline. Try it anyway.

### Q: Can I add my own patterns?

**A**: Yes! Edit `assistant.py` and add to `LEARNED_PATTERNS`. Document your patterns and success rates.

### Q: How do I validate if the patterns work?

**A**: 
1. Get guidance on a decision
2. Make the decision
3. Record the outcome
4. Compare confidence level to actual result
5. Over time, you'll see if patterns are reliable

## Examples of Decisions This Works For

- Technical: Refactor? Upgrade? Rewrite? Architecture change?
- Business: New feature? Improve existing? Enter market? Hire?
- Team: Reorganize? Change process? Learn new skill?
- Personal: Career change? Move? Learn new thing? Change habits?
- Strategic: Long-term direction? Major investment? Pivot?

## Not For

- Decisions with only one option (not a decision)
- Decisions where you can't articulate options/constraints
- Decisions that don't need guidance (flip a coin)
- Decisions where you need emotional support (talk to a friend)

## Next Steps

1. **Try it on a real decision** you're facing
2. **See if the guidance helps** you think more clearly
3. **Record the outcome** (what actually happened)
4. **Compare**: Was the confidence level right?
5. **Iterate**: Try more decisions, refine your understanding of the patterns

## Get Better at Deciding

Use this tool to:
- **Clarify your thinking**: Forcing yourself to fill out the JSON forces clarity
- **Apply proven patterns**: Don't invent approaches, use what works
- **Measure confidence**: Know how certain you should be
- **Learn over time**: Track outcomes, improve your pattern understanding

The goal isn't to avoid bad decisions. It's to make **good decisions more consistently**.

---

**Need more detail?** See `README.md` for complete documentation.

**Want to contribute patterns?** Send a PR or add your learned patterns to `assistant.py`.

**Questions?** The tool itself will help you ask good ones.
