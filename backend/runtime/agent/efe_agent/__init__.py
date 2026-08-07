"""efe_agent — Active Inference agent for GraphWorld.

Uses Expected Free Energy (EFE) for goal selection and Policy Templates
for action organisation, replacing hard-coded priority chains and
LLM-as-arbiter decision making.
"""

from .world_belief import WorldBelief, RoomBelief, NodeBelief
from .efe_model import GenerativeModel, graphworld_model
from .goal_transition_model import (
    GoalSignature, HierarchicalGoalTransitionModel,
    enrich_goal_signature, goal_signature,
)
from .efe_scorer import (
    score_goal, select_goal, select_goal_generative, decompose_goal,
    goal_action_index,
)
from .thinker_post import (
    observe_deviations, goal_outcome, thinker_update, urgency_to_obs,
)
from .efe_goal_builder import goal_still_needed
from .efe_core import EfeLoop, efe_agent

__all__ = [
    "WorldBelief", "RoomBelief", "NodeBelief",
    "GenerativeModel", "graphworld_model",
    "GoalSignature", "HierarchicalGoalTransitionModel",
    "goal_signature", "enrich_goal_signature",
    "score_goal", "select_goal", "select_goal_generative", "decompose_goal",
    "goal_action_index",
    "observe_deviations", "goal_outcome", "thinker_update", "urgency_to_obs",
    "goal_still_needed",
    "EfeLoop", "efe_agent",
]
