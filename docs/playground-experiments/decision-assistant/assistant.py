#!/usr/bin/env python3
"""
Decision Assistant: Help others make better decisions

This tool extracts learned patterns from meta-learning and decision analysis
and applies them to help external users/agents make better decisions.

Unlike the Decision Predictor (which analyzes the system), this tool is designed
to be useful OUTSIDE the system - for anyone facing a decision problem.
"""

import json
import sys
from pathlib import Path
from typing import TypedDict, Optional, List


class DecisionProblem(TypedDict, total=False):
    """A decision problem that needs guidance"""
    name: str
    description: str
    options: List[str]
    constraints: List[str]
    timeline: str  # "immediate", "short-term", "medium-term", "long-term"
    reversibility: str  # "reversible", "partially-reversible", "irreversible"
    information_level: str  # "incomplete", "moderate", "complete"
    stakes: str  # "low", "medium", "high"


class DecisionGuidance(TypedDict, total=False):
    """Structured guidance for a decision"""
    decision_name: str
    analysis: str
    recommended_approach: str
    key_questions: List[str]
    risk_factors: List[str]
    success_patterns: List[str]
    confidence_level: float  # 0.0-1.0


# Learned patterns from iterations 28-37
LEARNED_PATTERNS = {
    "modular_design": {
        "principle": "Breaking problems into independent modules increases success",
        "success_rate": 0.95,
        "applicable_to": ["complex problems", "long-term projects", "cross-domain work"],
        "guidance": [
            "Identify independent subproblems",
            "Solve each in isolation first",
            "Then integrate at clear boundaries",
            "This reduces complexity and allows parallel progress"
        ]
    },
    "interface_implementation_separation": {
        "principle": "Clear separation between interface (external API) and implementation increases robustness",
        "success_rate": 0.95,
        "applicable_to": ["systems", "tools", "frameworks"],
        "guidance": [
            "Define the external contract clearly first",
            "Let internal implementation vary without breaking contract",
            "This allows improvement without breaking users",
            "Easier to test, easier to change"
        ]
    },
    "honest_measurement": {
        "principle": "Measuring actual outcomes (not predicted/hoped) drives better decisions",
        "success_rate": 0.95,
        "applicable_to": ["all decisions with outcomes"],
        "guidance": [
            "Define what success actually looks like",
            "Measure it objectively post-decision",
            "Record both successes and failures",
            "Use actual data to improve future decisions"
        ]
    },
    "breadth_then_depth": {
        "principle": "Exploring broadly first, then diving deep, leads to better solutions than single-track focus",
        "success_rate": 0.90,
        "applicable_to": ["learning", "exploration", "innovation"],
        "guidance": [
            "Spend time understanding multiple approaches",
            "Identify which approach aligns with your constraints",
            "Then go deep on that approach",
            "This avoids narrow local optima"
        ]
    },
    "validation_changes_behavior": {
        "principle": "Adding measurement/validation systems actually changes how you work - usually for the better",
        "success_rate": 0.85,
        "applicable_to": ["process improvement", "quality"],
        "guidance": [
            "Validation isn't just measurement, it's learning",
            "The act of validating forces clarity",
            "This clarity leads to better decisions naturally",
            "Expect behavior to change when you add validation"
        ]
    },
    "timing_matters": {
        "principle": "Same decision at different times has different outcomes",
        "success_rate": 0.85,
        "applicable_to": ["time-dependent problems"],
        "guidance": [
            "Consider: Is this the right time for this decision?",
            "Short-term timing (<1 week): Build on recent momentum",
            "Medium-term (1-4 weeks): Allow learning from recent experiments",
            "Long-term (>1 month): Plan foundations carefully",
            "Wrong timing ruins good decisions"
        ]
    },
    "reversibility_matters": {
        "principle": "Reversible decisions should be made differently than irreversible ones",
        "success_rate": 0.85,
        "applicable_to": ["all decisions"],
        "guidance": [
            "Reversible: Low info → try it anyway, learn from outcome",
            "Partially reversible: Medium info → be more careful",
            "Irreversible: High info → only proceed with confidence",
            "Reversibility is your friend - use it"
        ]
    },
    "recursive_analysis_trap": {
        "principle": "Analyzing analysis (meta-analysis) can trap you in loops",
        "success_rate": 0.80,
        "applicable_to": ["complex decisions", "system design"],
        "guidance": [
            "One level of analysis is useful",
            "Two levels reveals patterns (useful)",
            "Three+ levels: You're analyzing the analysis of the analysis",
            "Stop when recursion stops producing new insights",
            "Build something with your insights, don't analyze them further"
        ]
    }
}

# Timing-based guidance
TIMING_GUIDANCE = {
    "immediate": {
        "guideline": "Decide now. Your window is closing.",
        "advice": [
            "Use pattern matching from recent experience",
            "Minimize analysis paralysis",
            "Trust your recent learning",
            "Act decisively"
        ]
    },
    "short-term": {
        "guideline": "Decide in days/1 week. Balance speed and care.",
        "advice": [
            "Do quick analysis",
            "Identify key uncertainties",
            "Can you test assumptions?",
            "Move on decision date"
        ]
    },
    "medium-term": {
        "guideline": "Decide in 1-4 weeks. Time to learn.",
        "advice": [
            "Design small experiments to reduce uncertainty",
            "Talk to relevant people",
            "Build prototype/mock/simulation",
            "Let learnings guide decision"
        ]
    },
    "long-term": {
        "guideline": "Decide in 1+ months. Plan carefully.",
        "advice": [
            "Invest in understanding",
            "Build strong foundations",
            "Plan for reversibility where possible",
            "This timeline allows careful work"
        ]
    }
}

# Reversibility guidance
REVERSIBILITY_GUIDANCE = {
    "reversible": {
        "guideline": "You can undo this. Be bolder.",
        "threshold": 0.30,  # Lower confidence threshold acceptable
        "strategy": "Try it, measure outcome, adjust"
    },
    "partially-reversible": {
        "guideline": "You can partly undo this. Be balanced.",
        "threshold": 0.60,  # Medium confidence needed
        "strategy": "Plan reversibility explicitly, test, have backup plan"
    },
    "irreversible": {
        "guideline": "This is permanent. Be very careful.",
        "threshold": 0.85,  # High confidence needed
        "strategy": "Extensive analysis, simulation, validation before proceeding"
    }
}


class DecisionAssistant:
    """Main assistant for providing decision guidance"""
    
    def __init__(self):
        self.patterns = LEARNED_PATTERNS
        self.timing_guidance = TIMING_GUIDANCE
        self.reversibility_guidance = REVERSIBILITY_GUIDANCE
    
    def analyze(self, problem: DecisionProblem) -> DecisionGuidance:
        """
        Analyze a decision problem and return guidance
        
        Args:
            problem: The decision problem to analyze
            
        Returns:
            Structured guidance for the decision
        """
        guidance: DecisionGuidance = {
            "decision_name": problem.get("name", "Unnamed Decision"),
            "analysis": self._analyze_problem(problem),
            "recommended_approach": self._recommend_approach(problem),
            "key_questions": self._generate_questions(problem),
            "risk_factors": self._identify_risks(problem),
            "success_patterns": self._identify_patterns(problem),
            "confidence_level": self._estimate_confidence(problem)
        }
        return guidance
    
    def _analyze_problem(self, problem: DecisionProblem) -> str:
        """Generate analysis of the decision problem"""
        parts = []
        
        # Timeline analysis
        timeline = problem.get("timeline", "medium-term")
        parts.append(f"Timeline: {self.timing_guidance[timeline]['guideline']}")
        
        # Reversibility analysis
        reversibility = problem.get("reversibility", "partially-reversible")
        rev_guidance = self.reversibility_guidance[reversibility]
        parts.append(f"Reversibility: {rev_guidance['guideline']}")
        
        # Information level analysis
        info_level = problem.get("information_level", "moderate")
        if info_level == "incomplete":
            parts.append("⚠️  You're deciding with incomplete information. Plan for learning.")
        elif info_level == "complete":
            parts.append("✓ You have complete information. Decision should be more definitive.")
        else:
            parts.append("You have moderate information. Some experimentation may help.")
        
        # Constraints
        constraints = problem.get("constraints", [])
        if constraints:
            parts.append(f"Constraints: {', '.join(constraints)}")
        
        return "\n".join(parts)
    
    def _recommend_approach(self, problem: DecisionProblem) -> str:
        """Recommend a decision-making approach"""
        timeline = problem.get("timeline", "medium-term")
        reversibility = problem.get("reversibility", "partially-reversible")
        
        base_approach = self.timing_guidance[timeline]["advice"]
        rev_strategy = self.reversibility_guidance[reversibility]["strategy"]
        
        return f"{rev_strategy}\n\nFor this timeline:\n" + \
               "\n".join(f"• {item}" for item in base_approach)
    
    def _generate_questions(self, problem: DecisionProblem) -> List[str]:
        """Generate key questions to ask about the decision"""
        questions = [
            "What happens if I'm wrong about this decision?",
            "What would I need to know to feel 80% confident?",
            "Can I test this assumption before committing fully?",
            "What's the worst case if this goes wrong?",
            "What's the best case if this goes right?",
            "How would I know if I made a good decision? (measurement)",
            "Is the timing right for this decision now?",
            "What patterns from past decisions apply here?"
        ]
        
        # Add specific questions based on problem type
        if len(problem.get("options", [])) > 3:
            questions.insert(0, "Can I reduce options to the truly distinct choices?")
        
        if problem.get("stakes") == "high":
            questions.insert(0, "What's my contingency if this fails?")
        
        return questions
    
    def _identify_risks(self, problem: DecisionProblem) -> List[str]:
        """Identify risk factors in the decision"""
        risks = []
        
        info_level = problem.get("information_level", "moderate")
        if info_level == "incomplete":
            risks.append("Incomplete information - hidden unknowns possible")
        
        stakes = problem.get("stakes", "medium")
        if stakes == "high":
            risks.append("High stakes - errors are costly")
        
        reversibility = problem.get("reversibility", "partially-reversible")
        if reversibility == "irreversible":
            risks.append("Irreversible - no going back after decision")
        
        timeline = problem.get("timeline", "medium-term")
        if timeline == "immediate":
            risks.append("Time pressure - less analysis possible")
        
        return risks
    
    def _identify_patterns(self, problem: DecisionProblem) -> List[str]:
        """Identify which success patterns apply"""
        applicable = []
        
        description = problem.get("description", "").lower()
        
        # Simple pattern matching
        if any(word in description for word in ["complex", "large", "system", "module"]):
            applicable.append("Modular Design: Break into independent pieces")
        
        if any(word in description for word in ["tool", "framework", "api", "interface"]):
            applicable.append("Interface/Implementation Separation: Define contract first")
        
        if any(word in description for word in ["measure", "outcome", "result", "test"]):
            applicable.append("Honest Measurement: Track actual vs. expected")
        
        if any(word in description for word in ["learn", "explore", "breadth", "option"]):
            applicable.append("Breadth Then Depth: Explore multiple approaches first")
        
        if any(word in description for word in ["validate", "check", "quality", "verify"]):
            applicable.append("Validation Changes Behavior: Measurement itself improves work")
        
        return applicable
    
    def _estimate_confidence(self, problem: DecisionProblem) -> float:
        """Estimate confidence level for this decision"""
        confidence = 0.5  # Start at 50%
        
        # Information level
        info_level = problem.get("information_level", "moderate")
        if info_level == "complete":
            confidence += 0.25
        elif info_level == "incomplete":
            confidence -= 0.15
        
        # Reversibility
        reversibility = problem.get("reversibility", "partially-reversible")
        if reversibility == "reversible":
            confidence += 0.10  # Easier to commit to reversible decisions
        elif reversibility == "irreversible":
            confidence -= 0.10  # Harder to commit to irreversible decisions
        
        # Apply reversibility threshold
        threshold = self.reversibility_guidance[reversibility]["threshold"]
        if confidence < threshold:
            confidence = min(confidence, threshold)
        
        # Cap at 0.95 (no certainty)
        return min(max(confidence, 0.0), 0.95)


def format_guidance(guidance: DecisionGuidance) -> str:
    """Format guidance for human reading"""
    output = []
    output.append(f"\n{'='*70}")
    output.append(f"DECISION GUIDANCE: {guidance['decision_name']}")
    output.append(f"{'='*70}\n")
    
    output.append("ANALYSIS:")
    output.append(guidance['analysis'])
    output.append("")
    
    output.append("RECOMMENDED APPROACH:")
    output.append(guidance['recommended_approach'])
    output.append("")
    
    output.append("SUCCESS PATTERNS THAT APPLY:")
    for pattern in guidance['success_patterns']:
        output.append(f"  • {pattern}")
    output.append("")
    
    output.append("RISK FACTORS:")
    for risk in guidance['risk_factors']:
        output.append(f"  ⚠️  {risk}")
    output.append("")
    
    output.append("KEY QUESTIONS TO ASK:")
    for i, q in enumerate(guidance['key_questions'], 1):
        output.append(f"  {i}. {q}")
    output.append("")
    
    confidence_pct = int(guidance['confidence_level'] * 100)
    output.append(f"CONFIDENCE LEVEL: {confidence_pct}%")
    
    if confidence_pct >= 75:
        output.append("→ You're well-positioned for this decision")
    elif confidence_pct >= 50:
        output.append("→ You should gather more information or test assumptions")
    else:
        output.append("→ This decision needs more planning or should be deferred")
    
    output.append(f"\n{'='*70}\n")
    
    return "\n".join(output)


def main():
    """Main entry point for CLI"""
    if len(sys.argv) < 2:
        print("Usage: decision-assistant <problem-json-file>")
        print("\nExample JSON:")
        example = {
            "name": "Should I refactor this module?",
            "description": "We have a complex module that's getting harder to maintain",
            "options": ["Refactor now", "Refactor later", "Leave as-is"],
            "constraints": ["Limited time", "Critical to production"],
            "timeline": "medium-term",
            "reversibility": "partially-reversible",
            "information_level": "complete",
            "stakes": "high"
        }
        print(json.dumps(example, indent=2))
        sys.exit(1)
    
    # Load problem
    problem_file = Path(sys.argv[1])
    if not problem_file.exists():
        print(f"Error: File not found: {problem_file}")
        sys.exit(1)
    
    with open(problem_file) as f:
        problem = json.load(f)
    
    # Analyze
    assistant = DecisionAssistant()
    guidance = assistant.analyze(problem)
    
    # Output
    print(format_guidance(guidance))
    
    # Save JSON version
    output_file = problem_file.parent / f"{problem_file.stem}_guidance.json"
    with open(output_file, 'w') as f:
        json.dump(guidance, f, indent=2)
    print(f"Detailed guidance saved to: {output_file}")


if __name__ == "__main__":
    main()
