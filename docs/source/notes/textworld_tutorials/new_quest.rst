Chapter 8: Design A Quest
==========================

A quest is a basic structure to define milestone and goals for a game. It defines that how the strategy of the game
should be shaped as well as the winning policy of an RL agent. Each quest includes five parts as given below,

::

    win_event:  A Combination of mutually exclusive set of winning events.
    fail_event: A Combination of mutually exclusive set of winning events.
    reward:     Reward given for completing this quest.
                By default, reward is set to 1 if there is at least one winning events otherwise it is set to 0.
    desc:       A text description of the quest.
    commands:   List of text commands leading to this quest completion.

Either the win or fail events are a combination of several events; this combination can be defined as "OR" or "AND" of
the events. If the events are combined using OR logic, at least one of the events should be triggered to complete the
quest; this combination is implemented by "EventOr" class. It is described in `combined event <~./combined_event.rst>`_
tutorial, described in section A. Similarly, if the events are combined such that all should be triggered to complete
the quest, then the combination follows the AND logic and is described in section B of the
`combined event <~./combined_event.rst>`_ tutorial.

During the process of the game design, the "new_quest" method of GameMaker is required. This method takes all inputs
for the Quest class and generates the quest object. The followings are three examples of the design of a quest, which
include either win or fail sets of events as well as the assigned rewards;

::

    quest_1 = game.new_quest(win_event=game.new_combination(and_combination=[win_event_1, win_event_2]),
                             fail_event=game.new_combination(or_combination=[fail_event_1, fail_event_2]),
                             reward=5)

    quest_2 = game.new_quest(win_event=game.new_combination(and_combination=[win_event_1, game.new_combination(or_combination=[win_event_2, win_event_3])]),
                             reward=-2)

    quest_3 = game.new_quest(win_event=game.new_combination(and_combination=[win_event_1]),
                             reward=0)

The quest_1 contains both wining and failing sets. If the players follows the strategy in which it triggers both
win_event_1 and win_event_2, the the quest is satisfied and the reward of 5 is achieved. However, if the game continues
such that either of fail_event_1 or fail_event_2 are triggered, then the game will fail.

In the quest_2, there are two combined events recursive respect to each other. So to satisfy this quest, the win_event_1
and at least one of win_event_2 or win_event_3 should be triggered. However, the reward is negative, which means that if
such scenario happens, the player will be punished but won't fail the game. This type of quest is useful to teach the
player those prohibited actions where lead the player to fail or to get far from the goal.

Finally, the third quest (quest_3) carries the reward of 0. This quest is usually employed when the game designer wants
to only adds some traceables (the propositions which have some kind of past verb tenses) to the game state. Thus, the
event(s) of this quest is (are) supposed to have the verb_tense definitions for some of its (their) propositions. That
way, when the event is triggered, those verb-tensed-equipped propositions (i.e. traceables) are added to the game's
state.

