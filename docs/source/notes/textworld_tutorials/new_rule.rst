Chapter 5: How To Design A New Rule For The Game?
=================================================

Rules in TextWorld are actually the general format of a specific action. For instance, the general format of the rule of
opening a box is given as

::

    open/c1 :: $at(P, r) & $at(s, r) & $on(c, s) & closed(c) -> open(c);

where this box is on the supporter (s) ad the box and the player both are at the room (r). This rule includes rule name
and  two sets of propositions; preconditions and postconditions, respectively, at the left and the right of the arrow.
The precondition indicates a subset of the propositions of the game state which are necessary to be available in the
state to be potentially possible to trigger the rule. Any proposition in the precondition which is equipped with "$"
means that it is going to be unchanged on the postcondition side; i.e. the <$at(P, r)> is valid and stays the same
before and after of happening this rule. The <closed(c)> proposition is changing to <open(c)> proposition when the box
is opened.

The rule becomes an action, when it is specified to entities of the game; e.g. assume that the supporter's name is
identified as s_0, the box's name is as c_0, etc. Then the action of the open/c1 rule is defined as

::

    open/c1 :: $at(P, r_0:r) & $at(s_0:s, r_0:r) & $on(c_0:c, s_0:s) & closed(c_0:c) -> open(c_0:c);

Hence, the difference between a rule and an action is their general and specified definitions to the same thing.
To have an action, the game first requires to have its rule be defined. Some basic rules are  defined for TextWorld.
However, it is also possible to define new rules for the game. In the next two sections, two different methods of
defining a new rule are described.

A. Defining a new conditions for a basic Rule
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Assume that the designer wants to define a new version to the open/c1 rule in which this rule is available when the
email has been read in addition to all open/c1's preconditions. Thus, in the logic files (the .twl files), this new
rule can be defined as follows:

::

    rules {
        ... [list of all previous rules]

        open/c1 :: $at(P, r) & $at(s, r) & $on(c, s) & closed(c) -> open(c);
        open/c2 :: $at(P, r) & $at(s, r) & $on(c, s) & $has_been__read/e(cpu) & closed(c) -> open(c);

    }

    inform7 {
        ...
        commands {
            ... [inform7 definition of other commands]

            open/c1 :: "open {c}" :: "opening the {c}";
            open/c2 :: "open {c}" :: "opening the {c}";
        }

where the proposition of <has_been__read/e(cpu)> is mandatory for the precondition set of the second rule, although its
inform7 command (i.e. Human's language command) is the same. This means that when either an RL agent or the player
observes the "open c_0" command, based on the number of the valid propositions in the game state, the player can reach
to open/c1 or open/c2 actions, depends on the maximum number of the available valid propositions. Each game could have
several rules for the same purpose but with various preconditions. This feature is important when it comes to design a
quest for the game, in which the designer can manage to create sequence of some actions as the strategy for the game to
gain some rewards, and if those sequences don't happen completely, the reward won't be gained. The procedure of the
quest design and the importance of the preconditions of a rule are all described in `quest <~./new_quest.rst>`_ tutorial
with details and applicable examples.

B. Create a completely  new Rule
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is also possible that a new rule, beyond the basic rules of the framework, should be defined for the game. This
mechanism is described at Chapter 2 in the Section E which is called as
"Defining a new command to Inform7". For more details please check `logic <~./designing_new_logic.rst>`_.