# Decision Assistant

**A practical tool for making better decisions**

Unlike most decision tools, this doesn't analyze *you*. It helps *you* make better decisions by applying learned patterns from successful decision-making.

## What It Does

The Decision Assistant takes a decision problem and provides:

1. **Analysis** - What's the situation? (timeline, reversibility, information level)
2. **Recommended Approach** - How should you tackle this?
3. **Success Patterns** - Which proven patterns apply to your situation?
4. **Risk Factors** - What could go wrong?
5. **Key Questions** - What should you ask yourself?
6. **Confidence Level** - How well-positioned are you for this decision?

## Who It's For

- Anyone facing a complex decision
- Teams needing decision frameworks
- Agents/systems making autonomous choices
- People wanting to learn from empirically-proven patterns

## The Patterns It Uses

The tool is built on patterns learned from 10 iterations of complex decision-making:

- **Modular Design** (95% success): Break problems into independent pieces
- **Interface/Implementation Separation** (95% success): Define the contract, vary the internals
- **Honest Measurement** (95% success): Measure actual outcomes, not hoped outcomes
- **Breadth Then Depth** (90% success): Explore broadly before going deep
- **Validation Changes Behavior** (85% success): Measurement itself improves work
- **Timing Matters** (85% success): Same decision at different times has different outcomes
- **Reversibility Matters** (85% success): Reversible decisions are safer, should be bolder
- **Avoid Recursive Analysis** (80% success): One level of analysis is useful, three+ is a trap

## Usage

### Basic Usage

```bash
cd /workspace/decision-assistant

# Create a problem file
cat > my_decision.json << 'EOF'
{
  "name": "Should I refactor this module?",
  "description": "We have a complex module that's getting harder to maintain",
  "options": ["Refactor now", "Refactor later", "Leave as-is"],
  "constraints": ["Limited time", "Critical to production"],
  "timeline": "medium-term",
  "reversibility": "partially-reversible",
  "information_level": "complete",
  "stakes": "high"
}
EOF

# Get guidance
python3 assistant.py my_decision.json
```

### Input Format

```json
{
  "name": "Description of what you're deciding",
  "description": "More detailed context about the decision",
  "options": ["Option A", "Option B", "Option C"],
  "constraints": ["Constraint 1", "Constraint 2"],
  "timeline": "immediate|short-term|medium-term|long-term",
  "reversibility": "reversible|partially-reversible|irreversible",
  "information_level": "incomplete|moderate|complete",
  "stakes": "low|medium|high"
}
```

### Output

You get two outputs:

1. **Human-readable guidance** (printed to terminal)
2. **JSON guidance** (saved to `{name}_guidance.json`)

## Examples

### Example 1: Technical Refactoring

```json
{
  "name": "Refactor authentication module",
  "description": "Module has grown complex, test coverage is poor, but it's working",
  "options": ["Refactor now", "Refactor later", "Leave as-is"],
  "constraints": ["Limited time", "Critical to security"],
  "timeline": "medium-term",
  "reversibility": "partially-reversible",
  "information_level": "complete",
  "stakes": "high"
}
```

**Expected Guidance**: Modular Design and Interface/Implementation Separation patterns apply. High stakes + time availability = cautious but committed approach.

### Example 2: Feature Development Decision

```json
{
  "name": "Build new feature or improve existing?",
  "description": "We can either build requested feature or improve performance of existing tool",
  "options": ["Build new feature", "Improve existing", "Do both in parallel"],
  "constraints": ["Team capacity for one track"],
  "timeline": "long-term",
  "reversibility": "reversible",
  "information_level": "incomplete",
  "stakes": "medium"
}
```

**Expected Guidance**: Long timeline + incomplete information → Breadth Then Depth pattern. Reversibility means you can try the less obvious option.

### Example 3: Quick Decision Under Pressure

```json
{
  "name": "Emergency bug fix approach",
  "description": "Critical bug in production, need to decide: patch quickly or investigate root cause",
  "options": ["Quick patch", "Root cause fix", "Hybrid (patch + investigate)"],
  "constraints": ["Customer impact growing by the minute"],
  "timeline": "immediate",
  "reversibility": "reversible",
  "information_level": "incomplete",
  "stakes": "high"
}
```

**Expected Guidance**: Immediate timeline + high stakes + reversible = Act decisively. Quick patch is defensible because you can improve it later.

## How the Confidence Level Works

The tool estimates your confidence for the decision based on:

- **Information level**: Complete info ↑ confidence, incomplete ↓
- **Reversibility**: Reversible decisions can be bolder, irreversible must be careful
- **Applied patterns**: Decisions aligned with proven patterns ↑ confidence

The confidence estimate tells you:

- **75%+**: You're well-positioned for this decision
- **50-75%**: Gather more information or test assumptions
- **<50%**: This needs more planning or should be deferred

## Integration Examples

### In a Team Decision Process

```bash
# 1. Identify decision
# 2. Fill out problem.json
# 3. Run assistant to get guidance
python3 assistant.py problem.json

# 4. Use guidance to structure team discussion
# 5. Make decision
# 6. Record what happened
# 7. (Optional) Update patterns based on outcome
```

### In an Autonomous System

```python
from decision_assistant.assistant import DecisionAssistant

assistant = DecisionAssistant()
guidance = assistant.analyze(decision_problem)

# Use guidance to inform decision logic
if guidance['confidence_level'] >= 0.75:
    proceed_with_decision()
else:
    gather_more_information()
```

### For Decision Retrospectives

```bash
# After making a decision, compare:
# 1. What did the assistant predict?
# 2. What actually happened?
# 3. What would you do differently?
# 4. Should the patterns be updated?
```

## Design Philosophy

This tool is intentionally:

- **Practical**: Gives you actionable guidance, not philosophical analysis
- **Pattern-based**: Uses empirically-proven patterns, not vague heuristics
- **Humble**: Estimates confidence, doesn't claim certainty
- **Extensible**: Easy to add new patterns as you learn
- **Honest**: Lists risk factors alongside guidance
- **External**: Helps *you* decide, doesn't analyze *you*

## What Makes This Different

Most decision tools fall into two categories:

1. **Analysis of you**: Personality tests, decision-making style assessments
2. **Analysis of the problem**: Pro/con lists, decision matrices

This tool is different: **It applies patterns from successful decisions to your specific situation.**

Think of it as learning from people who made similar decisions before and succeeded.

## Limitations

The tool works best when:

- ✓ You have clear decision options
- ✓ You can articulate constraints
- ✓ The decision has precedents (similar decisions made before)
- ✓ You want structured guidance, not just brainstorming

The tool has limits when:

- ✗ Decision is completely novel (no relevant patterns)
- ✗ You need team dynamics help (this is individual guidance)
- ✗ You want someone to decide for you (this helps you decide)

## Future Extensions

Possible improvements:

- **Outcome tracking**: Record what happened, update confidence scores
- **Pattern learning**: Add new patterns as you make more decisions
- **Comparative analysis**: See how this decision compares to similar past decisions
- **Team mode**: Multi-person decision guidance
- **Domain-specific patterns**: Technical, business, personal decision patterns

## About the Patterns

The patterns in this tool come from 10 iterations of complex decision-making about building autonomous systems. Each pattern has an empirically-measured success rate:

- Patterns at 90%+ success are highly confident
- Patterns at 80-90% are reliable with caveats
- Patterns at 70-80% work often but have exceptions

This is real-world learning, not theory.

## Examples in the Repository

See `/workspace/decision-assistant/examples/` for more example problems and how the tool handles them.

## Questions?

The tool itself will help you ask good questions. That's the point.
