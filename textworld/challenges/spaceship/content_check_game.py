import argparse
import os

from os.path import join as pjoin
from typing import Mapping, Optional

import textworld

from textworld import g_rng
from textworld import GameMaker
from textworld.challenges import register
from textworld.generator.data import KnowledgeBase
from textworld.generator.game import GameOptions

from textworld.generator.game import EventCondition, EventAction, EventOr, EventAnd, AbstractEvent, Quest


g_rng.set_seed(20190826)
PATH = os.path.dirname(__file__)


def build_argparser(parser=None):
    parser = parser or argparse.ArgumentParser()

    group = parser.add_argument_group('Content_check game settings')
    group.add_argument("--level", required=True, choices=["easy", "medium", "difficult"],
                       help="The difficulty level. Must be between: easy, medium, or difficult.")
    general_group = argparse.ArgumentParser(add_help=False)
    general_group.add_argument("--third-party", metavar="PATH",
                               help="Load third-party module. Useful to register new custom challenges on-the-fly.")
    return parser


def make_game(settings: Mapping[str, str], options: Optional[GameOptions] = None) -> textworld.Game:
    """
    This is a simple environment to test that how the agent understands the text. In this setting, we have a couple of
    openable items in a single room, there is also a laptop which sends an email deterministically and indicates which
    item should be opened. The goal is to chack two following things:
        * whether the text is understood by the agent
        * which word is most important to the agent; i.e. which word triggers the agent to act accordingly



    :return:
    generated game be played by the agent
    """

    kb = KnowledgeBase.load(target_dir=pjoin(os.path.dirname(__file__), 'textworld_data'))
    options = options or GameOptions()
    options.grammar.theme = 'spaceship'
    options.kb = kb
    options.seeds = g_rng.seed

    if settings["level"] == 'easy':
        mode = "easy"
        options.nb_objects = 4
        box_colors = [
            'Red',
            'Blue',
            'White',
            'Green',
        ]

    elif settings["level"] == 'medium':
        mode = "medium"
        options.nb_objects = 6
        box_colors = [
            'Red',
            'Black',
            'white',
            'Green',
            'Blue',
            'Brown',
        ]

    elif settings["level"] == 'difficult':
        mode = "difficult"
        options.nb_objects = 8
        box_colors = [
            'Red',
            'Black',
            'white',
            'Green',
            'Blue',
            'Purple',
            'Brown',
            'Yellow',
        ]

    metadata = {"desc": "ContentDetection",  # Collect information for reproduction.
                "mode": mode,
                "seeds": options.seeds,
                "world_size": options.nb_rooms}

    # +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    #                                    Create the Game Environment
    # +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    gm = GameMaker(options=options)

    # ===== Sleep Station Design =======================================================================================
    test_room = gm.new_room("Test Room")
    test_room.infos.desc = "This is a room which includes a table, a laptop and {:} boxes. Each box has a color " \
                           "on it which is distinguished by. Using the laptop, the agent can check the message in " \
                           "which says which box should be open to give the agent the maximum score. The message is " \
                           "the best clue to win. ".format(options.nb_objects)

    table = gm.new(type='s', name='Table')
    table.infos.desc = "This is a regular table."
    test_room.add(table)

    laptop = gm.new(type='cpu', name='laptop')
    laptop.infos.desc = "This is a laptop which is on the table. You can do regular things with this, like check " \
                        "your emails, watch YouTube, Skype with family, etc. Check your emails to find out which " \
                        "box is important."
    table.add(laptop)
    gm.add_fact('unread/e', laptop)

    boxes = []
    for n in range(options.nb_objects):
        tp = gm.new(type='c', name="{:} box".format(box_colors[n]))
        tp.infos.desc = "This a {} box.".format(box_colors[n])
        table.add(tp)
        gm.add_fact("closed", tp)
        boxes.append(tp)

    # ===== Player and Inventory Design ================================================================================
    gm.set_player(test_room)

    game = quest_design(gm)

    from textworld.challenges.spaceship.maker import test_commands
    test_commands(gm, [
        'open Red box',
        'close Red box',
        'open Blue box',
        'check laptop for email',
        'open Blue box',
        'open Red box',
        'close Red box',
    ])

    game.metadata = metadata
    uuid = "tw-content_check-{level}".format(level=str.title(settings["level"]))
    game.metadata["uuid"] = uuid

    return game


def quest_design(game):
    quests = []

    for i in ['c_0', 'c_1', 'c_2', 'c_3']:
        event_1 = game.new_event(conditions={game.new_fact("unread/e",
                                                           game._entities['cpu_0'])},
                                 event_type="condition")
        event_2 = game.new_event(actions=game.new_action('open/c1',
                                                         game._entities['P'],
                                                         game._entities['r_0'],
                                                         game._entities['s_0'],
                                                         game._entities[i]),
                                 event_type="action")
        quests.append(game.new_quest(win_event=game.new_combination(and_combination=[event_1, event_2]),
                                     reward=-1))

    event_3 = game.new_event(conditions={game.new_fact("read/e", game._entities['cpu_0'])},
                             verb_tense={'read/e': 'has been'},
                             event_type="condition")
    quests.append(game.new_quest(win_event=game.new_combination(and_combination=[event_3]),
                                 reward=0))

    event_4 = game.new_event(actions=game.new_action('open/c',
                                                     game._entities['P'],
                                                     game._entities['r_0'],
                                                     game._entities['s_0'],
                                                     game._entities['c_0'],
                                                     game._entities['cpu_0']),
                             event_type="action")
    quests.append(game.new_quest(win_event=game.new_combination(and_combination=[event_4]),
                                 reward=5))

    game.quests = quests

    return game.build()


game = make_game({'level': 'easy'})


# register(name="tw-content_check",
#          desc="Generate a content check game",
#          make=make_game,
#          add_arguments=build_argparser)
