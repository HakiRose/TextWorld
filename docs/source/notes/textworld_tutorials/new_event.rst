Chapter 6: Design An Event
==========================

Events can be considered as check points for the game. They define what are the important spots during the game
as well as how the player performs when playing the game.
The player's performance is measured by how it achieves the intermediate goals and eventually reaches to the final goal.
Each game may includes one or more events.
Each event defines what game's state or action is important for us. Thus, two categories of events can be defined.

TextWorld supports both categories of events: EventCondition and EventAction. EventCondition is capable of tracking a
specific `propositions <~./verb_tens_and_propositions.rst>`_ of a state. This proposition can be time sensitive
(verb tense equipped propositions). The EventAction supports those events which are sensitive about the happening of
an action itself rather than its effect on the state of the game. In next to sections we describe these two events with
details.

A. EventCondition
-----------------
A-1. Introduction to the EventCondition class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Each EventCondition object includes the following inputs:

::

    conditions: Set of propositions which need to be all true in order for this event to get triggered.
    actions:    The actions to be performed to trigger this event.
                If an empty list, then `conditions` must be provided.
    commands:   Human readable version of the actions.
    **kwargs:   There are various elements that can be imported into this class:
                * verb_tense: The desired verb tense for any state propositions which are supposed to be tracking.
                * name: a customized name can be chosen for the object of the class

A game designer can define one or a combination of some propositions as an event. This means that when the game state
comes to the moment that the set of the event's propositions are all valid, then this event becomes true. As another
use case scenario for this class, if there is a series of commands (or equivalently actions) and the state of the game
after completing all these action is the goal of the event, the EventCondition is the best choice.

If any of the propositions, which are specified in this event and requires to be tracked during the rest of the game,
should be mentioned in the verb_tense with the corresponding verb tenses. Assume that three propositions are defined in
an event as follows:

::

    is__at(p, r_0:r),
    is__open(c_0:c),
    is__closed(d_0:d),

where means the player is at the room r_0, the box c_0 is open, and the door d_0 is closed in the state and this event
is satisfied. Let's assume that the open box status requires to be tracked as "the c_0 was open" already. This is
important when the game requires to activate the effect of <open box> one step later than the time it actually happens;
i.e. the game's designer wants to consider the opening of the box one step later arther than the current step. The other
proposition could be the <closed door> proposition, in which the designer wants to track this forever during the game,
although the door would be opened later. This could be translated by either "the d_0 has been closed" or "the d_0 had
been closed" (the difference is described in `here <~./verb_tens_and_propositions.rst>`_). Let's assume that the chosen
verb tense is <has been closed>. In the verb_tense, these two tracings can be defined by using a dictionary. The keys
of the dictionary are the proposition's name and the values of the dictionary is the verb tenses. The following is an
example of how to create the traceable propositions for our above example:

::

    verb_tense = {'open': 'was', 'closed': 'has been'}

The traceable propositions are appeared as *was__open(c_0:c)* and *has_been__closed(d_0:d)* in the state set.

A-2. Define a proposition in EventCondition class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The "new_fact" method in "GameMaker" class is designed to help the game designer to define a specific proposition
of the game as event. This method takes the name of the new fact which is basically the name of the proposition and
the list of its entities, which uses the "_entities" method of the same class for each single entity. As an instance,
the proposition for an open door is "is__open(d_0:d)", which the prop name is "open" and the entity's name is "d_0".
The proposition for an unread email is "is_unread/e(cpu_0:cpu)", which the name is "unread/e" and the entity's name is
"cpu_0"; and, the proposition for a box on the table is "is__on(c_0:c, s_0:s)", which has two entities, respectively as,
"c_0" and "s_0". Each of these propositions can be defined as follows,

::

    {game.new_fact("open", game._entities['d_0']),
     game.new_fact("unread/e", game._entities['cpu_0']),
     game.new_fact("on", game._entities['c_0'], game._entities['s_0'])}

where 'game' is the object of the GameMaker class. If the designing event includes more than one proposition, each
proposition requires one new_fact structure and all of them should be stacked to create a combination of propositions
for the event, as it's been done in above example.

A-3. Event class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
In previous version of the TextWorld the EventCondition class used to be called as Event class. The current version is
compatible with the old version, and all those games which were designed based on this class can be run with no error.
In fact, both Event and EventCondition classes are the same and both monitor the state of the game.

B. EventAction
--------------
B-1. Introduction to the EventAction class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The EventAction class is designed to define those events that are actually sensitive to happening of an action rather
than the state of the game after that action (like what the EventCondition matters to). The object of this class
includes the following inputs:

::

    action:     The action to be performed to trigger this event.
    actions:    This is supposed to be empty for this class.
    commands:   Human readable version of the actions.
    **kwargs:   There are various elements that can be imported into this class:
                * verb_tense: The desired verb tense for any state propositions which are supposed to be tracking.
                * name: a customized name can be chosen for the object of the class


Since this class is sensitive to the moment that an action triggers, and at each step of the game only one action can
happen; thus, this event can usually be defined for single action. Each action (or `rule <~./new_rule.rst>`_ ) includes
two sets of precondition and postcondition propositions. Any proposition from the rule's postcondition can be assigned
to be traced within the rest of the game. To do that, the proposition(s) should be defined in the "verb_tense" via one
of the supported verb tenses.

B-2. Define an action in the EventAction class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
An action for an event is designed by using the "new_action" method of the GameMaker class. This method takes the rule
of the action from the game's knowledge library as well as all entities of the action; i.e. all required entities of
precondition and postcondition propositions. The following is an example to create an open action to a box (c_0) which
is on the table (s_0) at the room (r_0). The first line describes how the action is and the second line represents how
it can be created by using the new_action.

::

    open/c1 :: $at(P, r_0:r) & $at(s_0:s, r_0:r) & $on(c_0:c, s_0:s) & closed(c_0:c) -> open(c_0:c);

    game.new_action('open/c1',
                    game._entities['P'],
                    game._entities['r_0'],
                    game._entities['s_0'],
                    game._entities['c_0']),


Define an Event for the Game
----------------------------
The EventCondition and EventAction are, respectively, used to define a state or an action for an event. To create the
event, the "new_event" method from the GameMaker class should be called. This method enables the game designer to create
any type of the events. This method takes the following inputs:

::

    actions:              The action to define an event, which is sensitive to the action.
    conditions:           Set of propositions of the state which are required for an event, which is sensitive to the state of the game.
    commands:             Human readable version of the actions,
    event_type:           Indicates that the event is state-based or action-based event;
                          its default is on 'condition', which means the state.
    **kwargs:             It includes any required kwargs for the EventAction or EventCondition classes, such as the verb tense.

Therefore, defining a new event for the game is basically starts by calling the GameMaker.new_event. By using the
event_style entity, the type of the event is indicated and basically could design various strategies for the game. The
below examples represent that how this method enables the game to react to two different scenarios. The first event
targets the state (i.e. the EventCondition) in which the email (cpu_0) is read, and this proposition is supposed to be
traced with "has been" verb tense, where means forever during the game. The second event tracks the triggering of the
action (an EventAction) in which the box c_0 is being opened. This event does npt include any traceable.

::

    event_1 = game.new_event(condition={game.new_fact("read/e", game._entities['cpu_0'])},
                             verb_tense={'read/e': 'has been'},
                             event_type='condition')

    event_2 = game.new_event(action={game.new_action("open/c1",
                                                     game._entities['P'],
                                                     game._entities['r_0'],
                                                     game._entities['s_0'],
                                                     game._entities['c_0'],
                                                     game._entities['cpu_0'])},
                             event_type='action')

Defining the events is required step to define any `quest <~./new_quest.rst>`_.
Events can be combined with each other abd create more complex events and/or quests. This combination is described in
`event combination <~./combined_event.rst>`_ chapter.

