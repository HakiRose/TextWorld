Chapter 7: Combined Events
==========================

As described in `event <~./new_event.rst>`_ design chapter, an event defines a trigger point of the game. Events can be
combined to each other and create more complex event and consequently more complex quests. The combination basically
means that how the trigger response from each of these events can be add to each other and how indicates the final
outcome, as a True or False flag to evaluate the quest where holds these combined events. Combination basically divided
into two categories: the "OR" and "AND" combinations, where the AND or OR terms come from logic relations.

When two elements are combined with AND logic, both should be True to result a True output. For the OR combination, it
needs at least one True event. The boolean logic mechanism follows the "Disjunctive Normal Form" (DNF) rule.
A logical formula is considered to be in DNF if it is a disjunction (OR combination) of one or more conjunctions
(AND combination) of one or more logical statements. There are two basic event combinations supported by TextWorld:
EventOr and EventAnd.

A. EventOr
-----------------
The EventOr class takes the list of events and combines them with each other. The "events" entity of the class stores
the events which are combined to each other. These events can be any of EventAction, EventCondition, EventAnd, or
EventOr object. For the first two event classes see `event <~./new_event.rst>`_. At each step of the game, events of the
EventOr are evaluated according to the DNF boolean normalization to see if the combined events are triggered.
The EventOr class is considered as to be triggered when at least one of its events is triggered by the action which is
taken at each step of the game.

To create a sample of this class, first, there should be at least one event. The process of designing an event is
described in `event <~./new_event.rst>`_. Then, the "new_combination" method of GameMaker is called. This method has two
imports: and_combination and or_combination. At each combination definition, only one of them can be assigned by the
list of events. To define an EventOr, the or_combination is called as follows:

::

    game.new_combination(or_combination=[event_1, event_2])

where it's assumed that event_1 and event_2 are already defined in this example.


B. EventAnd
-----------------
The EventAnd class is similar to EventOr; however, the "AND" combination insists that all the events should be triggered
where in result the EventAnd turns to be True. The rest of this class is very similar to the EventOr section.

To define a sample of this class, the process is very similar to the EventOr, the only exception is occurred at the
calling entity of the new_combination method. See the following example for details

::

    game.new_combination(and_combination=[event_1, event_2])

where the and_combination is called to create the EventAnd sample.


How do more complex combinations perform?
------------------------------------------
As we described before, the combined events can be defined recursively. However, they follow the DNF boolean logic to
normalize the expression. The transformation of a combined events are performed by the "AbstractEvent.to_dnf(expr)"
in which the combination of events are imported through the expr. In this section, various examples of these
combinations are analyzed and the outcome is represented. This outcome defines that how the combined event can be
triggered. At each example, we first define the expression, as expr, as it is described above; then, the DNF
normalization is applied, and finally the logical outcome is presented.

Example 1:
""""""""""
Two events combined with an EventOr, i.e. EventOr(events=[event_1, event_2])

::

    expr = game.new_combination(or_combination= [event_1,event_2])
    output = AbstractEvent.to_dnf(expr)

    output:
        EventOr(EventAnd(event_1),EventAnd(event_2))

Thus, either of event_1 or event_2 can become True such that the combination is triggered.

Example 2:
""""""""""
Two events combined with an EventAnd, i.e. EventAnd(events=[event_1, event_2])

::

    expr = game.new_combination(and_combination= [event_1,event_2])
    output = AbstractEvent.to_dnf(expr)

    output:
        EventOr(EventAnd(event_1, event_2))

Thus, both event_1 and event_2 should become True such that the combination is triggered.

Example 3:
""""""""""
Two recursive OR events are combined with each other, i.e. EventOr(events=[event_1, EventOr(events=[event_2, event_3])])

::

    expr = game.new_combination(or_combination= [event_1,
                                                 game.new_combination(or_combination= [event_2, event_3])
                                                 ])
    output = AbstractEvent.to_dnf(expr)

    output:
        EventOr(EventAnd(event_1), EventAnd(event_2), EventAnd(event_3))

Thus, either of the events become True, then the combination is triggered.

Example 4:
""""""""""
Two recursive combined events are integrated with each other, i.e. EventOr(events=[event_1, EventAnd(events=[event_2, event_3])])

::

    expr = game.new_combination(or_combination= [event_1,
                                                 game.new_combination(and_combination= [event_2, event_3])
                                                 ])
    output = AbstractEvent.to_dnf(expr)

    output:
        EventOr(EventAnd(event_1), EventAnd(event_2, event_3))

Thus, it is required that at least one of the AND combinations become True.

Example 5:
""""""""""
EventAnd(events=[event_1, EventOr(events=[event_2, event_3])])

::

    expr = game.new_combination(and_combination= [event_1,
                                                  game.new_combination(or_combination= [event_2, event_3])
                                                  ])
    output = AbstractEvent.to_dnf(expr)

    output:
        EventOr(EventAnd(event_1, event_2), EventAnd(event_1, event_3))

Example 6:
""""""""""
EventAnd(events=[event_1, EventAnd(events=[event_2, event_3])])

::

    expr = game.new_combination(and_combination= [event_1,
                                                  game.new_combination(and_combination= [event_2, event_3])
                                                  ])
    output = AbstractEvent.to_dnf(expr)

    output:
        EventOr(EventAnd(event_1, event_2, event_3))






