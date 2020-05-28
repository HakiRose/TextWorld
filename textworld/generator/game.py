# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.


import copy
import json
import textwrap
import itertools

from typing import List, Dict, Optional, Mapping, Any, Iterable, Union, Tuple
from collections import OrderedDict

from numpy.random import RandomState

from textworld import g_rng
from textworld.utils import encode_seeds
from textworld.generator.data import KnowledgeBase
from textworld.generator.text_grammar import Grammar, GrammarOptions
from textworld.generator.world import World
from textworld.logic import Action, Proposition, State, Rule
from textworld.generator.graph_networks import DIRECTIONS

from textworld.generator.chaining import ChainingOptions

from textworld.generator.dependency_tree import DependencyTree
from textworld.generator.dependency_tree import DependencyTreeElement


try:
    from typing import Collection
except ImportError:
    # Collection is new in Python 3.6 -- fall back on Iterable for 3.5
    from typing import Iterable as Collection


class UnderspecifiedEventError(NameError):
    def __init__(self):
        msg = "Either the actions or the conditions is needed to create an event."
        super().__init__(msg)


class UnderspecifiedQuestError(NameError):
    def __init__(self):
        msg = "At least one winning or failing event is needed to create a quest."
        super().__init__(msg)


class AbstractEvent:

    def __init__(self, actions: Iterable[Action] = (), commands: Iterable[str] = (), name: str = "",
                 verb_tense: dict = ()) -> None:
        """
        Args:
            actions: The actions to be performed to trigger this event.
            commands: Human readable version of the actions.
            verb_tense: The desired verb tense for any state propositions which are been tracking.
        """
        self.actions = actions
        self.commands = commands
        self.name = name
        self._verb_tense = verb_tense

    @property
    def actions(self) -> Iterable[Action]:
        return self._actions

    @actions.setter
    def actions(self, actions: Iterable[Action]) -> None:
        self._actions = tuple(actions)

    @property
    def commands(self) -> Iterable[str]:
        return self._commands

    @commands.setter
    def commands(self, commands: Iterable[str]) -> None:
        self._commands = tuple(commands)

    def __hash__(self) -> int:
        return hash((self.actions, self.commands))

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, AbstractEvent)
                and self.actions == other.actions
                and self.commands == other.commands
                and self.name == other.name
                and self._verb_tense == other._verb_tense)

    @classmethod
    def deserialize(cls, data: Mapping) -> Union["AbstractEvent", "EventCondition", "EventAction", "EventOr", "EventAnd"]:
        """ Creates a `AbstractEvent` (or one of its subtypes) from serialized data.

        Args:
            data: Serialized data with the needed information to build a `AbstractEvent` (or one of its subtypes) object.
        """
        if data["type"] == "EventCondition":
            obj = EventCondition.deserialize(data)
        elif data["type"] == "EventAction":
            obj = EventAction.deserialize(data)
        elif data["type"] == "EventOr":
            obj = EventOr.deserialize(data)
        elif data["type"] == "EventAnd":
            obj = EventAnd.deserialize(data)
        elif data["type"] == "AbstractEvent":
            obj = cls()

        obj.actions = [Action.deserialize(d) for d in data["actions"]]
        obj.commands = data["commands"]
        obj.name = data["name"]
        obj._verb_tense = data["verb"]
        return obj

    def serialize(self) -> Mapping:
        """ Serialize this event.

        Results:
            Event's data serialized to be JSON compatible
        """
        return {
            "type": self.__class__.__name__,
            "commands": self.commands,
            "actions": [action.serialize() for action in self.actions],
            "name": self.name,
            "verb": self._verb_tense
        }

    def copy(self) -> "AbstractEvent":
        """ Copy this event. """
        return self.deserialize(self.serialize())

    @classmethod
    def to_dnf(cls, expr: Optional["AbstractEvent"]) -> Optional["AbstractEvent"]:
        """Normalize a boolean expression to its DNF.

        Expr can be an AbstractEvent, it this case it returns EventOr([EventAnd([element])]).
        Expr can be an EventOr(...) / EventAnd(...) expressions,
        in which cases it returns also a disjunctive normalised form (removing identical elements)

        References:
            Code inspired by https://stackoverflow.com/a/58372345
        """
        if expr is None:
            return None

        if not isinstance(expr, (EventOr, EventAnd)):
            result = EventOr((EventAnd((expr,)),))

        elif isinstance(expr, EventOr):
            result = EventOr(se for e in expr for se in cls.to_dnf(e))

        elif isinstance(expr, EventAnd):
            total = []
            for c in itertools.product(*[cls.to_dnf(e) for e in expr]):
                total.append(EventAnd(se for e in c for se in e))

            result = EventOr(total)

        return result


class EventCondition(AbstractEvent):

    def __init__(self, conditions: Iterable[Proposition] = (),
                 actions: Iterable[Action] = (),
                 commands: Iterable[str] = (),
                 **kwargs) -> None:
        """
        Args:
            conditions: Set of propositions which need to be all true in order for this event
                        to get triggered.
            actions: The actions to be performed to trigger this event.
                     If an empty list, then `conditions` must be provided.
            commands: Human readable version of the actions.

            **kwargs includes any other variables such as name, verb tense, etc.
        """
        super(EventCondition, self).__init__(actions, commands, **kwargs)
        self.condition = self.set_conditions(conditions)

    def set_conditions(self, conditions: Iterable[Proposition]) -> Action:
        """
        Set the triggering conditions for this event.

        Args:
            conditions: Set of propositions which need to
                        be all true in order for this event
                        to get triggered.
        Returns:
            Action that can only be applied when all conditions are statisfied.
        """
        if not conditions:
            if len(self.actions) == 0:
                raise UnderspecifiedEventError()

            # The default winning conditions are the postconditions of the
            # last action in the quest.
            conditions = self.actions[-1].postconditions

        variables = sorted(set([v for c in conditions for v in c.arguments]))
        event = Proposition("event", arguments=variables)

        self.traceable = []
        if self._verb_tense:
            self.traceable = [Proposition(name=self._verb_tense[prop.definition].replace(' ', '_') + '__' + prop.definition,
                                          arguments=prop.arguments)
                              for prop in conditions if prop.definition in self._verb_tense.keys()]

        return Action("trigger", preconditions=conditions, postconditions=list(conditions) + [event])

    @property
    def traceable(self) -> Iterable[Proposition]:
        return self._traceable

    @traceable.setter
    def traceable(self, traceable: Iterable[Proposition]) -> None:
        self._traceable = tuple(traceable)

    def is_triggering(self, state: State, action: Optional[Action] = None, callback: Optional[callable] = None) -> bool:
        """ Check if this event would be triggered in a given state. """
        is_triggering = state.is_applicable(self.condition)
        if callback and is_triggering:
            callback(self)

        return is_triggering

    def __hash__(self) -> int:
        return hash((self.actions, self.commands, self.condition, self.traceable))

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, EventCondition)
                and super().__eq__(other)
                and self.condition == other.condition
                and self.traceable == other.traceable)

    def __str__(self) -> str:
        return str(self.condition)

    def __repr__(self) -> str:
        return "EventCondition(Action.parse('{}'), name={})".format(self.condition, self.name)

    @classmethod
    def deserialize(cls, data: Mapping) -> "EventCondition":
        """ Creates an `EventCondition` from serialized data.

        Args:
            data: Serialized data with the needed information to build a `EventCondition` object.
        """
        condition = Action.deserialize(data["condition"])
        event = cls(conditions=condition.preconditions)
        event.traceable = tuple(Proposition.deserialize(d) for d in data["traceable"])
        return event

    def serialize(self) -> Mapping:
        """ Serialize this event.

        Results:
            `EventCondition`'s data serialized to be JSON compatible.
        """
        data = super().serialize()
        data["condition"] = self.condition.serialize()
        data["traceable"] = [prop.serialize() for prop in self.traceable]
        return data


class Event:  # For backward compatibility.
    """
    Event happening in TextWorld.

    An event gets triggered when its set of conditions become all statisfied.

    .. warning:: Deprecated in favor of
    :py:class:`textworld.generator.EventCondition <textworld.generator.game.EventCondition>`.
    """

    def __new__(cls, actions: Iterable[Action] = (),
                conditions: Iterable[Proposition] = (),
                commands: Iterable[str] = ()):
        return EventCondition(actions=actions, conditions=conditions, commands=commands)


class EventAction(AbstractEvent):

    def __init__(self, action: Rule,
                 actions: Iterable[Action] = (),
                 commands: Iterable[str] = (),
                 **kwargs) -> None:
        """
        Args:
            action: The action to be performed to trigger this event.
            actions: The actions to be performed to trigger this event.
            commands: Human readable version of the actions.

            **kwargs includes any other variables such as name, verb tense, etc.
        """
        super(EventAction, self).__init__(actions, commands, **kwargs)
        self.action = action
        self.set_actions()

    def set_actions(self):
        self.traceable = []
        if self.action and self._verb_tense:
            self.traceable = [
                Proposition(name=self._verb_tense[prop.definition].replace(' ', '_') + '__' + prop.definition,
                            arguments=prop.parameters)
                for prop in self.action.postconditions if prop.definition in self._verb_tense]

    @property
    def traceable(self) -> Iterable[Proposition]:
        return self._traceable

    @traceable.setter
    def traceable(self, traceable: Iterable[Proposition]) -> None:
        self._traceable = tuple(traceable)

    def is_triggering(self, state: Optional[State] = None,
                      action: Optional[Action] = None,
                      callback: Optional[callable] = None) -> bool:
        """ Check if this event would be triggered for a given action. """
        if action is None:
            return False

        mapping = self.action.match(action)
        if mapping is None:
            return False

        is_triggering = all(
            ph.name == mapping[ph].name for ph in self.action.placeholders if ph.name != ph.type
        )
        if callback and is_triggering:
            callback(self)

        return is_triggering

    def __hash__(self) -> int:
        return hash((self.actions, self.commands, self.action, self.traceable))

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, EventAction)
                and super().__eq__(other)
                and self.action == other.action
                and self.traceable == other.traceable)

    def __str__(self) -> str:
        return str(self.action)

    def __repr__(self) -> str:
        return "EventAction(Rule.parse('{}'), name={})".format(self.action, self.name)

    @classmethod
    def deserialize(cls, data: Mapping) -> "EventAction":
        """ Creates an `EventAction` from serialized data.

        Args:
            data: Serialized data with the needed information to build a
                  `EventAction` object.
        """
        action = Rule.deserialize(data["action"])
        event = cls(action=action)
        event.traceable = tuple(Proposition.deserialize(d) for d in data["traceable"])
        return event

    def serialize(self) -> Mapping:
        """ Serialize this event.

        Results:
            `EventAction`'s data serialized to be JSON compatible.
        """
        data = super().serialize()
        data["action"] = self.action.serialize()
        data["traceable"] = [prop.serialize() for prop in self.traceable]
        return data


class EventOr(AbstractEvent):
    def __init__(self, events: Iterable[AbstractEvent] = ()):
        super().__init__()
        self.events = events
        if len(self.events) == 1:
            self.commands = self.events[0].commands
            self.actions = self.events[0].actions

    @property
    def events(self) -> Tuple[AbstractEvent]:
        return self._events

    @events.setter
    def events(self, events: Iterable[AbstractEvent]) -> None:
        self._events = tuple(events)

    def is_triggering(self, state: Optional[State] = None,
                      action: Optional[Action] = None,
                      callback: Optional[callable] = None) -> bool:
        """ Check if this event would be triggered for a given state and/or action. """
        is_triggering = any(event.is_triggering(state, action, callback) for event in self.events)
        if callback and is_triggering:
            callback(self)

        return is_triggering

    def __iter__(self) -> Iterable[AbstractEvent]:
        yield from self.events

    def __len__(self) -> int:
        return len(self.events)

    def __repr__(self) -> str:
        return "EventOr({!r})".format(self.events)

    def __str__(self) -> str:
        return "EventOr({})".format(self.events)

    def __hash__(self) -> int:
        return hash(self.events)

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, EventOr)
                and self.events == other.events)

    def serialize(self) -> Mapping:
        """ Serialize this EventOr.

        Results:
            EventOr's data serialized to be JSON compatible
        """
        data = super().serialize()
        data["events"] = [e.serialize() for e in self.events]
        return data

    @classmethod
    def deserialize(cls, data: Mapping) -> "EventOr":
        """ Creates a `EventOr` from serialized data.

        Args:
            data: Serialized data with the needed information to build a `EventOr` object.
        """
        return cls([AbstractEvent.deserialize(d) for d in data["events"]])


class EventAnd(AbstractEvent):
    def __init__(self, events: Iterable[AbstractEvent] = ()):
        super().__init__()
        self.events = events
        if len(self.events) == 1:
            self.commands = self.events[0].commands
            self.actions = self.events[0].actions

    @property
    def events(self) -> Tuple[AbstractEvent]:
        return self._events

    @events.setter
    def events(self, events: Iterable[AbstractEvent]) -> None:
        self._events = tuple(events)

    def is_triggering(self, state: Optional[State] = None,
                      action: Optional[Action] = None,
                      callback: Optional[callable] = None) -> bool:
        """ Check if this event would be triggered for a given state and/or action. """
        is_triggering = all(event.is_triggering(state, action, callback) for event in self.events)
        if callback and is_triggering:
            callback(self)

        return is_triggering

    def __iter__(self) -> Iterable[AbstractEvent]:
        yield from self.events

    def __len__(self) -> int:
        return len(self.events)

    def __repr__(self) -> str:
        return "EventAnd({!r})".format(self.events)

    def __str__(self) -> str:
        return "EventAnd({})".format(self.events)

    def __hash__(self) -> int:
        return hash(self.events)

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, EventAnd)
                and self.events == other.events)

    def serialize(self) -> Mapping:
        """ Serialize this EventAnd.

        Results:
            EventAnd's data serialized to be JSON compatible
        """
        data = super().serialize()
        data["events"] = [e.serialize() for e in self.events]
        return data

    @classmethod
    def deserialize(cls, data: Mapping) -> "EventAnd":
        """ Creates a `EventAnd` from serialized data.

        Args:
            data: Serialized data with the needed information to build a `EventAnd` object.
        """
        return cls([AbstractEvent.deserialize(d) for d in data["events"]])


class Quest:
    """ Quest representation in TextWorld.

    A quest is defined by a mutually exclusive set of winning events and
    a mutually exclusive set of failing events.

    Attributes:
        win_event: Mutually exclusive set of winning events. That is,
                   only one such event needs to be triggered in order
                   to complete this quest.
        fail_event: Mutually exclusive set of failing events. That is,
                    only one such event needs to be triggered in order
                    to fail this quest.
        reward: Reward given for completing this quest.
        desc: A text description of the quest.
        commands: List of text commands leading to this quest completion.
    """

    def __init__(self,
                 win_event: Optional[AbstractEvent] = None,
                 fail_event: Optional[AbstractEvent] = None,
                 reward: Optional[int] = None,
                 desc: Optional[str] = None,
                 commands: Iterable[str] = (),
                 **kwargs) -> None:
        """
        Args:
            win_event:  Mutually exclusive set of winning events. That is,
                        only one such event needs to be triggered in order
                        to complete this quest.
            fail_event: Mutually exclusive set of failing events. That is,
                        only one such event needs to be triggered in order
                        to fail this quest.
            reward: Reward given for completing this quest. By default,
                    reward is set to 1 if there is at least one winning events
                    otherwise it is set to 0.
            desc: A text description of the quest.
            commands: List of text commands leading to this quest completion.
        """
        if "win_events" in kwargs:
            win_event = kwargs["win_events"]
        if "fail_events" in kwargs:
            fail_event = kwargs["fail_events"]

        if win_event and not isinstance(win_event, AbstractEvent):
            win_event = EventOr(win_event)

        if fail_event and not isinstance(fail_event, AbstractEvent):
            fail_event = EventOr(fail_event)

        self.win_event = AbstractEvent.to_dnf(win_event)
        self.fail_event = AbstractEvent.to_dnf(fail_event)
        self.desc = desc
        self.commands = tuple(commands)

        # Unless explicitly provided, reward is set to 1 if there is at least
        # one winning events otherwise it is set to 0.
        self.reward = int(len(win_event) > 0) if reward is None else reward

        if self.win_event is None and self.fail_event is None:
            raise UnderspecifiedQuestError()

    @property
    def events(self) -> Iterable[EventAnd]:
        events = []
        if self.win_event:
            events += list(self.win_event)

        if self.fail_event:
            events += list(self.fail_event)

        return events

    @property
    def commands(self) -> Iterable[str]:
        return self._commands

    @commands.setter
    def commands(self, commands: Iterable[str]) -> None:
        self._commands = tuple(commands)

    def is_winning(self, state: Optional[State] = None, action: Optional[Action] = None) -> bool:
        """ Check if this quest is winning for a given state and/or after a given action. """
        return self.win_event.is_triggering(state, action)

    def is_failing(self, state: Optional[State] = None, action: Optional[Action] = None) -> bool:
        """ Check if this quest is failing for a given state and/or after a given action. """
        return self.fail_event.is_triggering(state, action)

    def __hash__(self) -> int:
        return hash((self.win_event, self.fail_event, self.reward, self.desc, self.commands))

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, Quest)
                and self.win_event == other.win_event
                and self.fail_event == other.fail_event
                and self.reward == other.reward
                and self.desc == other.desc
                and self.commands == other.commands)

    @classmethod
    def deserialize(cls, data: Mapping) -> "Quest":
        """ Creates a `Quest` from serialized data.

        Args:
            data: Serialized data with the needed information to build a
                  `Quest` object.
        """
        win_event = AbstractEvent.deserialize(data["win_event"]) if data["win_event"] else None
        fail_event = AbstractEvent.deserialize(data["fail_event"]) if data["fail_event"] else None
        commands = data.get("commands", [])
        reward = data["reward"]
        desc = data["desc"]
        return cls(win_event, fail_event, reward, desc, commands)

    def serialize(self) -> Mapping:
        """ Serialize this quest.

        Results:
            Quest's data serialized to be JSON compatible
        """
        return {
            "desc": self.desc,
            "reward": self.reward,
            "commands": self.commands,
            "win_event": self.win_event.serialize() if self.win_event else None,
            "fail_event": self.fail_event.serialize() if self.fail_event else None
        }

    def copy(self) -> "Quest":
        """ Copy this quest. """
        return self.deserialize(self.serialize())


#
# class Event:
#
#     def __init__(self, actions: Iterable[Action] = (), commands: Iterable[str] = ()) -> None:
#         """
#         Args:
#             actions: The actions to be performed to trigger this event.
#             commands: Human readable version of the actions.
#         """
#
#         self.actions = list(actions)
#
#         self.commands = commands
#
#     @property
#     def verb_tense(self) -> dict:
#         return self._verb_tense
#
#     @verb_tense.setter
#     def verb_tense(self, verb: dict) -> None:
#         self._verb_tense = verb
#
#     @property
#     def actions(self) -> Tuple[Action]:
#         return self._actions
#
#     @actions.setter
#     def actions(self, actions: Iterable[Action]) -> None:
#         self._actions = tuple(actions)
#
#     @property
#     def commands(self) -> Iterable[str]:
#         return self._commands
#
#     @commands.setter
#     def commands(self, commands: Iterable[str]) -> None:
#         self._commands = tuple(commands)
#
#     def __hash__(self) -> int:
#         return hash((self.actions, self.commands))
#
#     def __eq__(self, other: Any) -> bool:
#         return (isinstance(other, Event) and
#                 self.actions == other.actions and
#                 self.commands == other.commands)
#
#     @classmethod
#     def deserialize(cls, data: Mapping) -> "Event":
#         """ Creates an `Event` from serialized data.
#
#         Args:
#             data: Serialized data with the needed information to build a `Event` object.
#         """
#         actions = [Action.deserialize(d) for d in data["actions_Event"]]
#         return cls(actions, data["commands_Event"])
#
#     def serialize(self) -> Mapping:
#         """ Serialize this event.
#
#         Results:
#             `Event`'s data serialized to be JSON compatible.
#         """
#         return {"commands_Event": self.commands,
#                 "actions_Event": [action.serialize() for action in self.actions]}
#
#     def copy(self) -> "Event":
#         """ Copy this event. """
#         return self.deserialize(self.serialize())
#
#
# class EventCondition(Event):
#     def __init__(self, conditions: Iterable[Proposition] = (),
#                  verb_tense: dict = (),
#                  actions: Iterable[Action] = (),
#                  commands: Iterable[str] = (),
#                  ) -> None:
#         """
#         Args:
#             actions: The actions to be performed to trigger this event.
#                      If an empty list, then `conditions` must be provided.
#             conditions: Set of propositions which need to be all true in order for this event
#                         to get triggered.
#             commands: Human readable version of the actions.
#             verb_tense: The desired verb tense for any state propositions which are been tracking.
#         """
#         super(EventCondition, self).__init__(actions, commands)
#
#         self.verb_tense = verb_tense
#
#         self.condition = self.set_conditions(conditions)
#
#     def set_conditions(self, conditions: Iterable[Proposition]) -> Action:
#         """
#         Set the triggering conditions for this event.
#
#         Args:
#             conditions: Set of propositions which need to
#                         be all true in order for this event
#                         to get triggered.
#         Returns:
#             Action that can only be applied when all conditions are statisfied.
#         """
#         if not conditions:
#             if len(self.actions) == 0:
#                 raise UnderspecifiedEventError()
#
#             # The default winning conditions are the postconditions of the
#             # last action in the quest.
#             conditions = self.actions[-1].postconditions
#
#         event = PropositionControl(conditions, self.verb_tense)
#         self.traceable = event.traceable_propositions
#         condition = Action("trigger", preconditions=conditions, postconditions=list(conditions) + [event.addon])
#
#         return condition
#
#     def is_valid(self):
#         return isinstance(self.condition, Action)
#
#     def is_triggering(self, state: State, actions: Iterable[Action] = ()) -> bool:
#         """ Check if this event would be triggered in a given state. """
#
#         return state.is_applicable(self.condition)
#
#     @property
#     def traceable(self) -> Iterable[Proposition]:
#         return self._traceable
#
#     @traceable.setter
#     def traceable(self, traceable: Iterable[Proposition]) -> None:
#         self._traceable = tuple(traceable)
#
#     def __hash__(self) -> int:
#         return hash((self.actions, self.commands, self.condition, self.verb_tense, self.traceable))
#
#     def __eq__(self, other: Any) -> bool:
#         return (isinstance(other, EventCondition) and
#                 self.actions == other.actions and
#                 self.commands == other.commands and
#                 self.condition == other.condition and
#                 self.verb_tense == other.verb_tense and
#                 self.traceable == other.traceable)
#
#     @classmethod
#     def deserialize(cls, data: Mapping) -> "EventCondition":
#         """ Creates an `EventCondition` from serialized data.
#
#         Args:
#             data: Serialized data with the needed information to build a `EventCondotion` object.
#         """
#         actions = [Action.deserialize(d) for d in data["actions_EventCondition"]]
#         condition = Action.deserialize(data["condition_EventCondition"])
#         return cls(condition.preconditions, data["verb_tense_EventCondition"], actions, data["commands_EventCondition"])
#
#     def serialize(self) -> Mapping:
#         """ Serialize this event.
#
#         Results:
#             `EventCondition`'s data serialized to be JSON compatible.
#         """
#         return {"commands_EventCondition": self.commands,
#                 "actions_EventCondition": [action.serialize() for action in self.actions],
#                 "condition_EventCondition": self.condition.serialize(),
#                 "verb_tense_EventCondition": self.verb_tense}
#
#     def copy(self) -> "EventCondition":
#         """ Copy this event. """
#         return self.deserialize(self.serialize())
#
#
# class EventAction(Event):
#
#     def __init__(self, actions: Iterable[Action] = (),
#                  verb_tense: dict = (),
#                  commands: Iterable[str] = ()) -> None:
#         """
#         Args:
#             actions: The actions to be performed to trigger this event.
#             commands: Human readable version of the actions.
#             verb_tense: The desired verb tense for any state propositions which are been tracking.
#         """
#         super(EventAction, self).__init__(actions, commands)
#
#         if self.is_valid():
#             raise UnderspecifiedEventActionError
#
#         self.verb_tense = verb_tense
#
#         self.traceable = self.set_actions()
#
#     def set_actions(self):
#         traceable = []
#         for act in self.actions:
#             props = []
#             for p in act.all_propositions:
#                 if p not in props:
#                     props.append(p)
#
#             event = PropositionControl(props, self.verb_tense)
#             traceable.append(event.traceable_propositions)
#
#         return [prop for ar in traceable for prop in ar]
#
#     def is_valid(self):
#         return len(self.actions) != 1
#
#     def is_triggering(self, state: Optional[State] = None, actions: Tuple[Action] = ()) -> bool:
#         """ Check if this event would be triggered for a given action. """
#         if not actions:
#             return False
#
#         return all((actions[i] == self.actions[i] for i in range(len(actions))))
#
#     @property
#     def traceable(self) -> Iterable[Proposition]:
#         return self._traceable
#
#     @traceable.setter
#     def traceable(self, traceable: Iterable[Proposition]) -> None:
#         self._traceable = tuple(traceable)
#
#     def __hash__(self) -> int:
#         return hash((self.actions, self.commands, self.verb_tense, self.traceable))
#
#     def __eq__(self, other: Any) -> bool:
#         return (isinstance(other, EventAction) and
#                 self.actions == other.actions and
#                 self.commands == other.commands and
#                 self.verb_tense == other.verb_tense and
#                 self.traceable == other.traceable)
#
#     @classmethod
#     def deserialize(cls, data: Mapping) -> "EventAction":
#         """ Creates an `EventAction` from serialized data.
#
#         Args:
#             data: Serialized data with the needed information to build a
#                   `EventAction` object.
#         """
#         action = [Action.deserialize(d) for d in data["actions_EventAction"]]
#         return cls(action, data["verb_tense_EventAction"], data["commands_EventAction"])
#
#     def serialize(self) -> Mapping:
#         """ Serialize this event.
#
#         Results:
#             `EventAction`'s data serialized to be JSON compatible.
#         """
#         return {"actions_EventAction": [action.serialize() for action in self.actions],
#                 "commands_EventAction": self.commands,
#                 "verb_tense_EventAction": self.verb_tense,
#                 }
#
#     def copy(self) -> "EventAction":
#         """ Copy this event. """
#         return self.deserialize(self.serialize())
#
#
# class EventOr:
#     def __init__(self, events: Tuple =()):
#         self.events = events
#         self._any_triggered = False
#         self._any_untriggered = False
#
#     @property
#     def events(self) -> Tuple[Union[EventAction, EventCondition]]:
#         return self._events
#
#     @events.setter
#     def events(self, events) -> None:
#         self._events = tuple(events)
#
#     def are_triggering(self, state, action):
#         status = []
#         for ev in self.events:
#             if isinstance(ev, EventCondition) or isinstance(ev, EventAction):
#                 status.append(ev.is_triggering(state, [action]))
#                 continue
#             status.append(ev.are_triggering(state, action))
#
#         return any(status)
#
#     def are_events_triggered(self, state, action):
#         return any((ev.is_triggering(state, action) for ev in self.events))
#
#     def __hash__(self) -> int:
#         return hash(self.events)
#
#     def __eq__(self, other: Any) -> bool:
#         return (isinstance(other, EventOr)
#                 and self.events == other.events)
#
#     def serialize(self) -> Mapping:
#         """ Serialize this EventOr.
#
#         Results:
#             EventOr's data serialized to be JSON compatible
#         """
#         return {"events_EventOr": [ev.serialize() for ev in self.events]}
#
#     @classmethod
#     def deserialize(cls, data: Mapping) -> "EventOr":
#         """ Creates a `EventOr` from serialized data.
#
#         Args:
#             data: Serialized data with the needed information to build a `EventOr` object.
#         """
#         events = []
#         for d in data["events_EventOr"]:
#             if "condition_EventCondition" in d.keys():
#                 events.append(EventCondition.deserialize(d))
#             elif "actions_EventAction" in d.keys():
#                 events.append(EventAction.deserialize(d))
#             elif "actions_Event" in d.keys():
#                 events.append(Event.deserialize(d))
#             elif "events_EventAnd" in d.keys():
#                 events.append(EventAnd.deserialize(d))
#             elif "events_EventOr" in d.keys():
#                 events.append(EventOr.deserialize(d))
#
#         return cls(events)
#
#     def copy(self) -> "EventOr":
#         """ Copy this EventOr. """
#         return self.deserialize(self.serialize())
#
#
# class EventAnd:
#     def __init__(self, events: Tuple = ()):
#         self.events = events
#         self._all_triggered = False
#         self._all_untriggered = False
#
#     @property
#     def events(self) -> Tuple[Union[EventAction, EventCondition]]:
#         return self._events
#
#     @events.setter
#     def events(self, events) -> None:
#         self._events = tuple(events)
#
#     def are_triggering(self, state, action):
#         status = []
#         for ev in self.events:
#             if isinstance(ev, EventCondition) or isinstance(ev, EventAction):
#                 status.append(ev.is_triggering(state, [action]))
#                 continue
#             status.append(ev.are_triggering(state, action))
#         return all(status)
#
#     def are_events_triggered(self, state, action):
#         return all((ev.is_triggering(state, action) for ev in self.events))
#
#     def __hash__(self) -> int:
#         return hash(self.events)
#
#     def __eq__(self, other: Any) -> bool:
#         return (isinstance(other, EventAnd)
#                 and self.events == other.events)
#
#     def serialize(self) -> Mapping:
#         """ Serialize this EventAnd.
#
#         Results:
#             EventAnd's data serialized to be JSON compatible
#         """
#         return {"events_EventAnd": [ev.serialize() for ev in self.events]}
#
#     @classmethod
#     def deserialize(cls, data: Mapping) -> "EventAnd":
#         """ Creates a `EventAnd` from serialized data.
#
#         Args:
#             data: Serialized data with the needed information to build a `EventAnd` object.
#         """
#         events = []
#         for d in data["events_EventAnd"]:
#             if "condition_EventCondition" in d.keys():
#                 events.append(EventCondition.deserialize(d))
#             elif "actions_EventAction" in d.keys():
#                 events.append(EventAction.deserialize(d))
#             elif "actions_Event" in d.keys():
#                 events.append(Event.deserialize(d))
#             elif "events_EventAnd" in d.keys():
#                 events.append(EventAnd.deserialize(d))
#             elif "events_EventOr" in d.keys():
#                 events.append(EventOr.deserialize(d))
#
#         return cls(events)
#
#     def copy(self) -> "EventAnd":
#         """ Copy this EventAnd. """
#         return self.deserialize(self.serialize())
#
#
# class Quest:
#     """ Quest representation in TextWorld.
#
#     A quest is defined by a mutually exclusive set of winning events and
#     a mutually exclusive set of failing events.
#
#     Attributes:
#         win_events: Mutually exclusive set of winning events. That is,
#                     only one such event needs to be triggered in order
#                     to complete this quest.
#         fail_events: Mutually exclusive set of failing events. That is,
#                      only one such event needs to be triggered in order
#                      to fail this quest.
#         reward: Reward given for completing this quest.
#         desc: A text description of the quest.
#         commands: List of text commands leading to this quest completion.
#     """
#
#     def __init__(self,
#                  win_events: Iterable[Union[EventAnd, EventOr]] = (),
#                  fail_events: Iterable[Union[EventAnd, EventOr]] = (),
#                  reward: Optional[int] = None,
#                  desc: Optional[str] = None,
#                  commands: Iterable[str] = ()) -> None:
#         """
#         Args:
#             win_events: Mutually exclusive set of winning events. That is,
#                         only one such event needs to be triggered in order
#                         to complete this quest.
#             fail_events: Mutually exclusive set of failing events. That is,
#                          only one such event needs to be triggered in order
#                          to fail this quest.
#             reward: Reward given for completing this quest. By default,
#                     reward is set to 1 if there is at least one winning events
#                     otherwise it is set to 0.
#             desc: A text description of the quest.
#             commands: List of text commands leading to this quest completion.
#         """
#         self.win_events = win_events
#         self.fail_events = fail_events
#         self.desc = desc
#         self.commands = tuple(commands)
#
#         self.win_events_list = self.events_organizer(self.win_events)
#         self.fail_events_list = self.events_organizer(self.fail_events)
#
#         # Unless explicitly provided, reward is set to 1 if there is at least
#         # one winning events otherwise it is set to 0.
#         self.reward = int(len(win_events) > 0) if reward is None else reward
#
#         if len(self.win_events) == 0 and len(self.fail_events) == 0:
#             raise UnderspecifiedQuestError()
#
#     @property
#     def win_events(self) -> Iterable[Union[EventOr, EventAnd]]:
#         return self._win_events
#
#     @win_events.setter
#     def win_events(self, events: Iterable[Union[EventOr, EventAnd]]) -> None:
#         self._win_events = tuple(events)
#
#     @property
#     def win_events_list(self) -> Iterable[Union[EventOr, EventAnd]]:
#         return self._win_events_list
#
#     @win_events_list.setter
#     def win_events_list(self, events: Iterable[Union[EventOr, EventAnd]]) -> None:
#         self._win_events_list = tuple(events)
#
#     @property
#     def fail_events(self) -> Iterable[Union[EventOr, EventAnd]]:
#         return self._fail_events
#
#     @fail_events.setter
#     def fail_events(self, events: Iterable[Union[EventOr, EventAnd]]) -> None:
#         self._fail_events = tuple(events)
#
#     @property
#     def fail_events_list(self) -> Iterable[Union[EventOr, EventAnd]]:
#         return self._fail_events_list
#
#     @fail_events_list.setter
#     def fail_events_list(self, events: Iterable[Union[EventOr, EventAnd]]) -> None:
#         self._fail_events_list = tuple(events)
#
#     @property
#     def commands(self) -> Iterable[str]:
#         return self._commands
#
#     @commands.setter
#     def commands(self, commands: Iterable[str]) -> None:
#         self._commands = tuple(commands)
#
#     def event_organizer(self, combined_event=(), _events=[]):
#         if isinstance(combined_event, EventCondition) or isinstance(combined_event, EventAction):
#             _events.append(combined_event)
#             return
#
#         act = []
#         for event in combined_event.events:
#             out = self.event_organizer(event, act)
#             if out:
#                 for a in out:
#                     _events.append(a)
#
#         return (len(act) > 0 and len(act) > len(_events)) * act or (len(_events) > 0 and len(_events) > len(act)) * _events
#
#     def events_organizer(self, combined_events=()):
#         _events_ = []
#         for comb_ev in combined_events:
#             for ev in self.event_organizer(comb_ev, _events=[]):
#                 _events_.append(ev)
#
#         return _events_
#
#     def is_winning(self, state: Optional[State] = None, actions: Tuple[Action] = ()) -> bool:
#         """ Check if this quest is winning in that particular state. """
#
#         return any(event.are_triggering(state, actions) for event in self.win_events)
#
#     def is_failing(self, state: Optional[State] = None, actions: Tuple[Action] = ()) -> bool:
#         """ Check if this quest is failing in that particular state. """
#         return any(event.are_triggering(state, actions) for event in self.fail_events)
#
#     def __hash__(self) -> int:
#         return hash((self.win_events, self.fail_events, self.reward, self.desc, self.commands))
#
#     def __eq__(self, other: Any) -> bool:
#         return (isinstance(other, Quest)
#                 and self.win_events == other.win_events
#                 and self.fail_events == other.fail_events
#                 and self.reward == other.reward
#                 and self.desc == other.desc
#                 and self.commands == other.commands)
#
#     @classmethod
#     def deserialize(cls, data: Mapping) -> "Quest":
#         """ Creates a `Quest` from serialized data.
#
#         Args:
#             data: Serialized data with the needed information to build a
#                   `Quest` object.
#         """
#         win_events = []
#         for d in data["win_events"]:
#             if "events_EventOr" in d.keys():
#                 win_events.append(EventOr.deserialize(d))
#             elif "events_EventAnd" in d.keys():
#                 win_events.append(EventAnd.deserialize(d))
#
#         fail_events = []
#         for d in data["fail_events"]:
#             if "events_EventOr" in d.keys():
#                 fail_events.append(EventOr.deserialize(d))
#             elif "events_EventAnd" in d.keys():
#                 fail_events.append(EventAnd.deserialize(d))
#
#         commands = data.get("commands", [])
#         reward = data["reward"]
#         desc = data["desc"]
#         return cls(win_events, fail_events, reward, desc, commands)
#
#     def serialize(self) -> Mapping:
#         """ Serialize this quest.
#
#         Results:
#             Quest's data serialized to be JSON compatible
#         """
#         return {
#             "desc": self.desc,
#             "reward": self.reward,
#             "commands": self.commands,
#             "win_events": [event.serialize() for event in self.win_events],
#             "fail_events": [event.serialize() for event in self.fail_events]
#         }
#
#     def copy(self) -> "Quest":
#         """ Copy this quest. """
#         return self.deserialize(self.serialize())


class EntityInfo:
    """ Additional information about entities in the game. """
    __slots__ = ['id', 'type', 'name', 'noun', 'adj', 'desc', 'room_type', 'definite', 'indefinite', 'synonyms']

    def __init__(self, id: str, type: str) -> None:
        #: str: Unique name for this entity. It is used when generating
        self.id = id
        #: str: The type of this entity.
        self.type = type
        #: str: The name that will be displayed in-game to identify this entity.
        self.name = None
        #: str: The noun part of the name, if available.
        self.noun = None
        #: str: The adjective (i.e. descriptive) part of the name, if available.
        self.adj = None
        #: str: The definite article to use for this entity.
        self.definite = None
        #: str: The indefinite article to use for this entity.
        self.indefinite = None
        #: List[str]: Alternative names that can be used to refer to this entity.
        self.synonyms = None
        #: str: Text description displayed when examining this entity in the game.
        self.desc = None
        #: str: Type of the room this entity belongs to. It used to influence
        #:      its `name` during text generation.
        self.room_type = None

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, EntityInfo)
                and all(getattr(self, slot) == getattr(other, slot)
                        for slot in self.__slots__))

    def __hash__(self) -> int:
        return hash(tuple(getattr(self, slot) for slot in self.__slots__))

    def __str__(self) -> str:
        return "Info({}: {} | {})".format(self.name, self.adj, self.noun)

    @classmethod
    def deserialize(cls, data: Mapping) -> "EntityInfo":
        """ Creates a `EntityInfo` from serialized data.

        Args:
            data: Serialized data with the needed information to build a
                  `EntityInfo` object.
        """
        info = cls(data["id"], data["type"])
        for slot in cls.__slots__:
            setattr(info, slot, data.get(slot))

        return info

    def serialize(self) -> Mapping:
        """ Serialize this object.

        Results:
            EntityInfo's data serialized to be JSON compatible
        """
        return {slot: getattr(self, slot) for slot in self.__slots__}


class Game:
    """ Game representation in TextWorld.

    A `Game` is defined by a world and it can have quest(s) or not.
    Additionally, a grammar can be provided to control the text generation.
    """

    _SERIAL_VERSION = 1

    def __init__(self, world: World, grammar: Optional[Grammar] = None,
                 quests: Iterable[Quest] = ()) -> None:
        """
        Args:
            world: The world to use for the game.
            quests: The quests to be done in the game.
            grammar: The grammar to control the text generation.
        """
        self.world = world
        self.quests = tuple(quests)
        self.metadata = {}
        self._objective = None
        self._infos = self._build_infos()
        self.kb = world.kb

        self.change_grammar(grammar)

    @property
    def infos(self) -> Dict[str, EntityInfo]:
        """ Information about the entities in the game. """
        return self._infos

    def _build_infos(self) -> Dict[str, EntityInfo]:
        mapping = OrderedDict()
        for entity in self.world.entities:
            if entity not in mapping:
                mapping[entity.id] = EntityInfo(entity.id, entity.type)

        return mapping

    def copy(self) -> "Game":
        """ Make a shallow copy of this game. """
        game = Game(self.world, None, self.quests)
        game._infos = dict(self.infos)
        game._objective = self._objective
        game.metadata = dict(self.metadata)
        return game

    def change_grammar(self, grammar: Grammar) -> None:
        """ Changes the grammar used and regenerate all text. """

        self.grammar = grammar
        if self.grammar:
            from textworld.generator.text_generation import generate_text_from_grammar
            generate_text_from_grammar(self, self.grammar)

        # Check if we can derive a global winning policy from the quests.
        if self.grammar:
            from textworld.generator.text_generation import describe_event
            policy = GameProgression(self).winning_policy
            if policy:
                mapping = {k: info.name for k, info in self._infos.items()}
                commands = [a.format_command(mapping) for a in policy]
                self.metadata["walkthrough"] = commands
                self.objective = describe_event(AbstractEvent(policy), self, self.grammar)

    # def change_grammar(self, grammar: Grammar) -> None:
    #     """ Changes the grammar used and regenerate all text. """
    #
    #     self.grammar = grammar
    #     _gen_commands = gen_commands_from_actions
    #     if self.grammar:
    #         from textworld.generator.inform7 import Inform7Game
    #         from textworld.generator.text_generation import generate_text_from_grammar
    #         inform7 = Inform7Game(self)
    #         _gen_commands = inform7.gen_commands_from_actions
    #         generate_text_from_grammar(self, self.grammar)
    #         from textworld.generator.text_generation import describe_quests
    #         self.objective = describe_quests(self, self.grammar)
    #
    #     for quest in self.quests:
    #         # TODO: should have a generic way of generating text commands from actions
    #         #       instead of relying on inform7 convention.
    #         for event in quest.win_events_list:
    #             event.commands = _gen_commands(event.actions)
    #
    #         if quest.win_events_list:
    #             quest.commands = quest.win_events_list[0].commands
    #
    #     # Check if we can derive a global winning policy from the quests.
    #     if self.grammar:
    #         policy = GameProgression(self).winning_policy
    #         if policy:
    #             mapping = {k: info.name for k, info in self._infos.items()}
    #             commands = [a.format_command(mapping) for a in policy]
    #             self.metadata["walkthrough"] = commands
    #             self.objective = describe_event(AbstractEvent(policy), self, self.grammar)
    #             # self.objective = describe_event(EventCondition(actions=policy), self, self.grammar)

    def save(self, filename: str) -> None:
        """ Saves the serialized data of this game to a file. """
        with open(filename, 'w') as f:
            json.dump(self.serialize(), f)

    @classmethod
    def load(cls, filename: str) -> "Game":
        """ Creates `Game` from serialized data saved in a file. """
        with open(filename, 'r') as f:
            return cls.deserialize(json.load(f))

    @classmethod
    def deserialize(cls, data: Mapping) -> "Game":
        """ Creates a `Game` from serialized data.

        Args:
            data: Serialized data with the needed information to build a
                  `Game` object.
        """

        version = data.get("version", cls._SERIAL_VERSION)
        if version != cls._SERIAL_VERSION:
            msg = "Cannot deserialize a TextWorld version {} game, expected version {}"
            raise ValueError(msg.format(version, cls._SERIAL_VERSION))

        kb = KnowledgeBase.deserialize(data["KB"])
        world = World.deserialize(data["world"], kb=kb)
        game = cls(world)
        game.grammar_options = GrammarOptions(data["grammar"])
        game.quests = tuple([Quest.deserialize(d) for d in data["quests"]])
        game._infos = {k: EntityInfo.deserialize(v) for k, v in data["infos"]}
        game.metadata = data.get("metadata", {})
        game._objective = data.get("objective", None)

        return game

    def serialize(self) -> Mapping:
        """ Serialize this object.

        Results:
            Game's data serialized to be JSON compatible
        """
        data = {}
        data["version"] = self._SERIAL_VERSION
        data["world"] = self.world.serialize()
        data["grammar"] = self.grammar.options.serialize() if self.grammar else {}
        data["quests"] = [quest.serialize() for quest in self.quests]
        data["infos"] = [(k, v.serialize()) for k, v in self._infos.items()]
        data["KB"] = self.kb.serialize()
        data["metadata"] = self.metadata
        data["objective"] = self._objective

        return data

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, Game)
                and self.world == other.world
                and self.infos == other.infos
                and self.quests == other.quests
                and self.metadata == other.metadata
                and self._objective == other._objective)

    def __hash__(self) -> int:
        state = (self.world,
                 frozenset(self.quests),
                 frozenset(self.infos.items()),
                 self._objective)

        return hash(state)

    @property
    def max_score(self) -> int:
        """ Sum of the reward of all quests. """
        return sum(quest.reward for quest in self.quests)

    @property
    def command_templates(self) -> List[str]:
        """ All command templates understood in this game. """
        return sorted(set(cmd for cmd in self.kb.inform7_commands.values()))

    @property
    def directions_names(self) -> List[str]:
        return DIRECTIONS

    @property
    def objects_types(self) -> List[str]:
        """ All types of objects in this game. """
        return sorted(self.kb.types.types)

    @property
    def objects_names(self) -> List[str]:
        """ The names of all relevant objects in this game. """
        def _filter_unnamed_and_room_entities(e):
            return e.name and e.type != "r"

        entities_infos = filter(_filter_unnamed_and_room_entities, self.infos.values())
        return [info.name for info in entities_infos]

    @property
    def entity_names(self) -> List[str]:
        return self.objects_names + self.directions_names

    @property
    def objects_names_and_types(self) -> List[str]:
        """ The names of all non-player objects along with their type in this game. """
        def _filter_unnamed_and_room_entities(e):
            return e.name and e.type != "r"

        entities_infos = filter(_filter_unnamed_and_room_entities, self.infos.values())
        return [(info.name, info.type) for info in entities_infos]

    @property
    def verbs(self) -> List[str]:
        """ Verbs that should be recognized in this game. """
        # Retrieve commands templates for every rule.
        return sorted(set(cmd.split()[0] for cmd in self.command_templates))

    @property
    def win_condition(self) -> List[Collection[Proposition]]:
        """ All win conditions, one for each quest. """
        return [q.winning_conditions for q in self.quests]

    @property
    def objective(self) -> str:
        if self._objective is not None:
            return self._objective

        # TODO: Find a better way of describing the objective of the game with several quests.
        self._objective = "\n The next quest is \n".join(quest.desc for quest in self.quests if quest.desc)

        return self._objective

    @objective.setter
    def objective(self, value: str):
        self._objective = value

    @property
    def walkthrough(self) -> Optional[List[str]]:
        walkthrough = self.metadata.get("walkthrough")
        if walkthrough:
            return walkthrough

        # Check if we can derive a walkthrough from the quests.
        policy = GameProgression(self).winning_policy
        if policy:
            mapping = {k: info.name for k, info in self._infos.items()}
            walkthrough = [a.format_command(mapping) for a in policy]
            self.metadata["walkthrough"] = walkthrough

        return walkthrough


class ActionDependencyTreeElement(DependencyTreeElement):
    """ Representation of an `Action` in the dependency tree.

    The notion of dependency and ordering is defined as follows:

    * action1 depends on action2 if action1 needs the propositions
      added by action2;
    * action1 should be performed before action2 if action2 removes
      propositions needed by action1.
    """

    def depends_on(self, other: "ActionDependencyTreeElement") -> bool:
        """ Check whether this action depends on the `other`.

        Action1 depends on action2 when the intersection between
        the propositions added by action2 and the preconditions
        of the action1 is not empty, i.e. action1 needs the
        propositions added by action2.
        """
        return len(other.action.added & self.action._pre_set) > 0

    @property
    def action(self) -> Action:
        return self.value

    def is_distinct_from(self, others: List["ActionDependencyTreeElement"]) -> bool:
        """
        Check whether this element is distinct from `others`.

        We check if self.action has any additional information
        that `others` actions don't have. This helps us to
        identify whether a group of nodes in the dependency tree
        already contain all the needed information that self.action
        would bring.
        """
        new_facts = set(self.action.added)
        for other in others:
            new_facts -= other.action.added

        return len(new_facts) > 0

    def __lt__(self, other: "ActionDependencyTreeElement") -> bool:
        """ Order ActionDependencyTreeElement elements.

        Actions that remove information needed by other actions
        should be sorted further in the list.

        Notes:
            This is not a proper ordering, i.e. two actions
            can mutually removed information needed by each other.
        """
        def _required_facts(node):
            pre_set = set(node.action._pre_set)
            while node.parent is not None:
                pre_set |= node.parent.action._pre_set
                pre_set -= node.action.added
                node = node.parent

            return pre_set

        return len(other.action.removed & _required_facts(self)) > len(self.action.removed & _required_facts(other))

    def __str__(self) -> str:
        params = ", ".join(map(str, self.action.variables))
        return "{}({})".format(self.action.name, params)


class ActionDependencyTree(DependencyTree):

    def __init__(self, *args, kb: Optional[KnowledgeBase] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._kb = kb or KnowledgeBase.default()

    def remove(self, action: Action) -> Tuple[bool, Optional[Action]]:
        changed = super().remove(action)

        # The last action might have impacted one of the subquests.
        reverse_action = self._kb.get_reverse_action(action)
        if self.empty:
            return changed, reverse_action

        if reverse_action is not None:
            changed = self.push(reverse_action)
        elif self.push(action.inverse()):
            # The last action did impact one of the subquests
            # but there's no reverse action to recover from it.
            changed = True

        return changed, reverse_action

    def flatten(self) -> Iterable[Action]:
        """
        Generates a flatten representation of this dependency tree.

        Actions are greedily yielded by iteratively popping leaves from
        the dependency tree.
        """
        tree = self.copy()  # Make a copy of the tree to work on.
        last_reverse_action = None
        while len(tree.roots) > 0:
            # Use 'sort' to try leaves that doesn't affect the others first.
            for leaf in sorted(tree.leaves_elements):
                if leaf.action != last_reverse_action:
                    break  # Choose an action that avoids cycles.

            yield leaf.action
            _, last_reverse_action = tree.remove(leaf.action)

    def copy(self) -> "ActionDependencyTree":
        tree = super().copy()
        tree._kb = self._kb
        return tree


class EventProgression:
    """ EventProgression monitors a particular event.

    Internally, the event is represented as a dependency tree of
    relevant actions to be performed.
    """

    def __init__(self, event: AbstractEvent, kb: KnowledgeBase) -> None:
        """
        Args:
            quest: The quest to keep track of its completion.
        """
        self._kb = kb or KnowledgeBase.default()
        self.event = event  # TODO: convert to dnf just to be safe.
        self._triggered = False
        self._untriggerable = False
        self._policy = None
        # self._policy = ()

        # Build a tree representations for each subevent.
        self._trees = []
        for events in self.event:  # Assuming self.event is in DNF.
            trees = []
            for event in events:
                tree = ActionDependencyTree(kb=self._kb, element_type=ActionDependencyTreeElement)

                if len(events.actions) > 0:
                    if isinstance(event, EventCondition):
                        tree.push(event.condition)

                    for action in events.actions[::-1]:
                        tree.push(action)

                trees.append(tree)

            trees = ActionDependencyTree(kb=self._kb,
                                         element_type=ActionDependencyTreeElement,
                                         trees=trees)
            self._trees.append(trees)

    @property
    def triggering_policy(self) -> Optional[List[Action]]:
        if self.done:
            return ()

        if self._policy is None or True:  # TODO
            policies = []
            for trees in self._trees:
                # Discard all "trigger" actions.
                policies.append(tuple(a for a in trees.flatten() if a.name != "trigger"))

            self._policy = min(policies, key=lambda policy: len(policy))

        return self._policy

    @property
    def _tree(self):
        best = None
        best_policy = None
        for trees in self._trees:
            # Discard all "trigger" actions.
            policy = tuple(a for a in trees.flatten() if a.name != "trigger")

            if best is None or len(best_policy) > len(policy):
                best = trees
                best_policy = policy

        return best

    @property
    def done(self) -> bool:
        """ Check if the quest is done (i.e. triggered or untriggerable). """
        return self.triggered or self.untriggerable

    @property
    def triggered(self) -> bool:
        """ Check whether the event has been triggered. """
        return self._triggered

    @property
    def untriggerable(self) -> bool:
        """ Check whether the event is in an untriggerable state. """
        return len(self._trees) == 0

    def update(self, action: Optional[Action] = None,
               state: Optional[State] = None,
               callback: Optional[callable] = None) -> None:
        """ Update event progression given available information.

        Args:
            action: Action potentially affecting the event progression.
            state: Current game state.
        """
        if self.done:
            return  # Nothing to do, the quest is already done.

        if state is not None:
            # Check if event is triggered.
            self._triggered = self.event.is_triggering(state, action, callback)

        # Update each dependency trees.
        to_delete = []
        for i, trees in enumerate(self._trees):
            if self._compress_policy(i, state):
                continue  # A shorter winning policy has been found.

            if action and not trees.empty:
                # Determine if we moved away from the goal or closer to it.
                changed, reverse_action = self._tree.remove(action)
                if changed and reverse_action is None:  # Irreversible action.
                    to_delete.append(trees)

                if changed and reverse_action is not None:
                    # Rebuild policy.
                    # self._policy = tuple(self._tree.flatten())
                    self._policy = None  # Will be rebuilt on the next call of triggering_policy.

        for e in to_delete:
            self._trees.remove(e)

    def _compress_policy(self, idx, state: State) -> bool:
        """ Compress the policy given a game state.

        Args:
            state: Current game state.

        Returns:
            Whether the policy was compressed or not.
        """
        # Make sure the compressed policy has the same roots.
        root_actions = [root.element.action for root in self._trees[idx].roots]

        def _find_shorter_policy(policy):
            for j in range(0, len(policy)):
                for i in range(j + 1, len(policy))[::-1]:
                    shorter_policy = policy[:j] + policy[i:]
                    if state.is_sequence_applicable(shorter_policy) and all(a in shorter_policy for a in root_actions):
                        self._trees[idx] = ActionDependencyTree(kb=self._kb, element_type=ActionDependencyTreeElement)
                        for action in shorter_policy[::-1]:
                            self._trees[idx].push(action, allow_multi_root=True)

                        return shorter_policy

            return None

        compressed = False
        policy = _find_shorter_policy(tuple(a for a in self._trees[idx].flatten()))
        while policy is not None:
            compressed = True
            policy = _find_shorter_policy(policy)

        return compressed


class QuestProgression:
    """ QuestProgression keeps track of the completion of a quest.

    Internally, the quest is represented as a dependency tree of
    relevant actions to be performed.
    """

    def __init__(self, quest: Quest, kb: KnowledgeBase) -> None:
        """
        Args:
            quest: The quest to keep track of its completion.
        """
        self.quest = quest
        self.win_event = EventProgression(quest.win_event, kb) if quest.win_event else None
        self.fail_event = EventProgression(quest.fail_event, kb) if quest.fail_event else None

    @property
    def _tree(self) -> Optional[List[ActionDependencyTree]]:
        return self.win_event._tree

    @property
    def winning_policy(self) -> Optional[List[Action]]:
        """ Actions to be performed in order to complete the quest. """
        if self.done or self.win_event is None:
            return None

        return self.win_event.triggering_policy

    @property
    def completable(self) -> bool:
        """ Check if the quest has winning events. """
        return self.win_event is not None

    @property
    def done(self) -> bool:
        """ Check if the quest is done (i.e. completed, failed or unfinishable). """
        return self.completed or self.failed or self.unfinishable

    @property
    def completed(self) -> bool:
        """ Check whether the quest is completed. """
        return self.win_event is not None and self.win_event.triggered

    @property
    def failed(self) -> bool:
        """ Check whether the quest has failed. """
        return self.fail_event is not None and self.fail_event.triggered

    @property
    def unfinishable(self) -> bool:
        """ Check whether the quest is in an unfinishable state. """
        return self.win_event.untriggerable if self.win_event else False

    def update(self, action: Optional[Action] = None,
               state: Optional[State] = None,
               callback: Optional[callable] = None) -> None:
        """ Update quest progression given available information.

        Args:
            action: Action potentially affecting the quest progression.
            state: Current game state.
        """
        if self.done:
            return  # Nothing to do, the quest is already done.

        if self.win_event:
            self.win_event.update(action, state, callback)

        if self.fail_event:
            self.fail_event.update(action, state, callback)


class GameProgression:
    """ GameProgression keeps track of the progression of a game.

    If `tracking_quests` is  True, then `winning_policy` will be the list
    of Action that need to be applied in order to complete the game.
    """

    def __init__(self, game: Game, track_quests: bool = True) -> None:
        """
        Args:
            game: The game for which to track progression.
            track_quests: whether quest progressions are being tracked.
        """
        self.game = game
        self.state = game.world.state.copy()
        self.callback = None
        self._valid_actions = list(self.state.all_applicable_actions(self.game.kb.rules.values(),
                                                                     self.game.kb.types.constants_mapping))

        self.quest_progressions = []
        if track_quests:
            self.quest_progressions = [QuestProgression(quest, game.kb) for quest in game.quests]
            for quest_progression in self.quest_progressions:
                quest_progression.update(action=None, state=self.state)

    @property
    def done(self) -> bool:
        """ Whether all quests are completed or at least one has failed or is unfinishable. """
        return self.completed or self.failed

    @property
    def completed(self) -> bool:
        """ Whether all completable quests are completed. """
        if not self.tracking_quests:
            return False  # There is nothing to be "completed".

        return all(qp.completed for qp in self.quest_progressions if qp.completable)

    @property
    def failed(self) -> bool:
        """ Whether at least one quest has failed or is unfinishable. """
        if not self.tracking_quests:
            return False  # There is nothing to be "failed".

        return any((qp.failed or qp.unfinishable) for qp in self.quest_progressions)

    @property
    def score(self) -> int:
        """ Sum of the reward of all completed quests. """
        return sum(qp.quest.reward for qp in self.quest_progressions if qp.completed)

    @property
    def tracking_quests(self) -> bool:
        """ Whether quests are being tracked or not. """
        return len(self.quest_progressions) > 0

    @property
    def valid_actions(self) -> List[Action]:
        """ Actions that are valid at the current state. """
        return self._valid_actions

    @property
    def winning_policy(self) -> Optional[List[Action]]:
        """ Actions to be performed in order to complete the game.

        Returns:
            A policy that leads to winning the game. It can be `None`
            if `tracking_quests` is `False` or the quest has failed.
        """
        if not self.tracking_quests:
            return None

        if self.done:
            return None

        # Greedily build a new winning policy by merging all quest trees.
        trees = [quest._tree for quest in self.quest_progressions if quest.completable and not quest.done]
        if None in trees:
            # Some quests don't have triggering policy.
            return None

        master_quest_tree = ActionDependencyTree(kb=self.game.kb,
                                                 element_type=ActionDependencyTreeElement,
                                                 trees=trees)

        # Discard all "trigger" actions.
        return tuple(a for a in master_quest_tree.flatten() if a.name != "trigger")

    def update(self, action: Action, callback: Optional[callable] = None) -> None:
        """ Update the state of the game given the provided action.

        Args:
            action: Action affecting the state of the game.
        """
        # Update world facts.
        self.state.apply(action)

        # Get valid actions.
        self._valid_actions = list(self.state.all_applicable_actions(self.game.kb.rules.values(),
                                                                     self.game.kb.types.constants_mapping))

        # Update all quest progressions given the last action and new state.
        for quest_progression in self.quest_progressions:
            quest_progression.update(action, self.state, callback or self.callback)


class GameOptions:
    """
    Options for customizing the game generation.

    Attributes:
        nb_rooms (int):
            Number of rooms in the game.
        nb_objects (int):
            Number of objects in the game.
        nb_parallel_quests (int):
            Number of parallel quests, i.e. not sharing a common goal.
        quest_length (int):
            Number of actions that need to be performed to complete the game.
        quest_breadth (int):
            Number of subquests per independent quest. It controls how nonlinear
            a quest can be (1: linear).
        quest_depth (int):
            Number of actions that need to be performed to solve a subquest.
        path (str):
            Path of the compiled game (.ulx or .z8). Also, the source (.ni)
            and metadata (.json) files will be saved along with it.
        force_recompile (bool):
            If `True`, recompile game even if it already exists.
        file_ext (str):
            Type of the generated game file. Either .z8 (Z-Machine) or .ulx (Glulx).
            If `path` already has an extension, this is ignored.
        seeds (Optional[Union[int, Dict]]):
            Seeds for the different generation processes.

               * If `None`, seeds will be sampled from
                 :py:data:`textworld.g_rng <textworld.utils.g_rng>`.
               * If `int`, it acts as a seed for a random generator that will be
                 used to sample the other seeds.
               * If dict, the following keys can be set:

                 * `'map'`: control the map generation;
                 * `'objects'`: control the type of objects and their
                   location;
                 * `'quest'`: control the quest generation;
                 * `'grammar'`: control the text generation.

                 For any key missing, a random number gets assigned (sampled
                 from :py:data:`textworld.g_rng <textworld.utils.g_rng>`).
        kb (KnowledgeBase):
            The knowledge base containing the logic and the text grammars (see
            :py:class:`textworld.generator.KnowledgeBase <textworld.generator.data.KnowledgeBase>`
            for more information).
        chaining (ChainingOptions):
            For customizing the quest generation (see
            :py:class:`textworld.generator.ChainingOptions <textworld.generator.chaining.ChainingOptions>`
            for the list of available options).
        grammar (GrammarOptions):
            For customizing the text generation (see
            :py:class:`textworld.generator.GrammarOptions <textworld.generator.text_grammar.GrammarOptions>`
            for the list of available options).
    """

    def __init__(self):
        self.chaining = ChainingOptions()
        self.grammar = GrammarOptions()
        self._kb = None
        self._seeds = None

        self.nb_parallel_quests = 1
        self.nb_rooms = 1
        self.nb_objects = 1
        self.force_recompile = False
        self.file_ext = ".ulx"
        self.path = "./tw_games/"

    @property
    def quest_length(self) -> int:
        assert self.chaining.min_length == self.chaining.max_length
        return self.chaining.min_length

    @quest_length.setter
    def quest_length(self, value: int) -> None:
        self.chaining.min_length = value
        self.chaining.max_length = value
        self.chaining.max_depth = value

    @property
    def quest_breadth(self) -> int:
        assert self.chaining.min_breadth == self.chaining.max_breadth
        return self.chaining.min_breadth

    @quest_breadth.setter
    def quest_breadth(self, value: int) -> None:
        self.chaining.min_breadth = value
        self.chaining.max_breadth = value

    @property
    def seeds(self):
        if self._seeds is None:
            self.seeds = {}  # Generate seeds from g_rng.

        return self._seeds

    @seeds.setter
    def seeds(self, value: Union[int, Mapping[str, int]]) -> None:
        keys = ['map', 'objects', 'quest', 'grammar']

        def _key_missing(seeds):
            return not set(seeds.keys()).issuperset(keys)

        seeds = value
        if type(value) is int:
            rng = RandomState(value)
            seeds = {}
        elif _key_missing(value):
            rng = g_rng.next()

        # Check if we need to generate missing seeds.
        self._seeds = {}
        for key in keys:
            if key in seeds:
                self._seeds[key] = seeds[key]
            else:
                self._seeds[key] = rng.randint(65635)

    @property
    def rngs(self) -> Dict[str, RandomState]:
        rngs = {}
        for key, seed in self.seeds.items():
            rngs[key] = RandomState(seed)

        return rngs

    @property
    def kb(self) -> KnowledgeBase:
        if self._kb is None:
            self.kb = KnowledgeBase.load()

        return self._kb

    @kb.setter
    def kb(self, value: KnowledgeBase) -> None:
        self._kb = value
        self.chaining.kb = self._kb

    def copy(self) -> "GameOptions":
        return copy.copy(self)

    @property
    def uuid(self) -> str:
        # TODO: generate uuid from chaining options?
        uuid = "tw-{specs}-{grammar}-{seeds}"
        uuid = uuid.format(specs=encode_seeds((self.nb_rooms, self.nb_objects, self.nb_parallel_quests,
                                               self.chaining.min_length, self.chaining.max_length,
                                               self.chaining.min_depth, self.chaining.max_depth,
                                               self.chaining.min_breadth, self.chaining.max_breadth)),
                           grammar=self.grammar.uuid,
                           seeds=encode_seeds([self.seeds[k] for k in sorted(self._seeds)]))
        return uuid

    def __str__(self) -> str:
        infos = ["-= Game options =-"]
        slots = ["nb_rooms", "nb_objects", "nb_parallel_quests", "path", "force_recompile", "file_ext", "seeds"]
        for slot in slots:
            infos.append("{}: {}".format(slot, getattr(self, slot)))

        text = "\n  ".join(infos)
        text += "\n  chaining options:\n"
        text += textwrap.indent(str(self.chaining), "    ")

        text += "\n  grammar options:\n"
        text += textwrap.indent(str(self.grammar), "    ")

        text += "\n  KB:\n"
        text += textwrap.indent(str(self.kb), "    ")
        return text
