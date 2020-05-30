# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.


"""
.. _the_cooking_game:
The Cooking Game
================
This type of game was used for the competition *First TextWorld Problems* [1]_.
The overall objective of the game is to locate the kitchen, read the cookbook,
fetch the recipe's ingredients, process them accordingly, prepare the meal, and
eat it. To control the game's difficulty, one can specify the amount of skills
that are involved to solve it (see skills section below).
Skills
------
    The required skills are:
    * recipe{1,2,3} : Number of ingredients in the recipe.
    The optional skills that can be combined are:
    * take{1,2,3} : Number of ingredients to fetch. It must be less
      or equal to the value of the `recipe` skill.
    * open : Whether containers/doors need to be opened.
    * cook : Whether some ingredients need to be cooked.
    * cut : Whether some ingredients need to be cut.
    * drop : Whether the player's inventory has limited capacity.
    * go{1,6,9,12} : Number of locations in the game.
Splits
------
    In addition to the skills, one can specify from which disjoint distribution
    the game should be generated from:
    * train : game use for training agent;
    * valid : game may contain food items (adj-noun pairs) unseen within
      the train split. It can also contain unseen food preparation;
    * test : game may contain food items (adj-noun pairs) unseen within
      the train split. It can also contain unseen food preparation.
References
----------
.. [1] https://competitions.codalab.org/competitions/20865
"""

import re
import itertools
import textwrap
from pprint import pprint

from typing import Mapping, Union, Dict, Optional, List

import numpy as np
import networkx as nx
from numpy.random import RandomState

import textworld
from textworld import GameMaker
from textworld.generator.maker import WorldRoom
from textworld.generator.game import Quest, Event, GameOptions
from textworld.generator.graph_networks import make_graph_world
from textworld.generator.graph_networks import DIRECTIONS, reverse_direction

from textworld.utils import encode_seeds

from textworld.challenges.utils import get_seeds_for_game_generation
from textworld.challenges import register

SKILLS = ["recipe", "take", "cook", "cut", "open", "drop", "go"]

FRESH_ADJECTIVES = ["fresh"]
ROTTEN_ADJECTIVES = ["rotten", "expired", "rancid"]

TYPES_OF_COOKING = ["raw", "fried", "roasted", "grilled"]
TYPES_OF_CUTTING = ["uncut", "chopped", "sliced", "diced"]

TYPES_OF_COOKING_VERBS = {"fried": "fry", "roasted": "roast", "grilled": "grill"}
TYPES_OF_CUTTING_VERBS = {"chopped": "chop", "sliced": "slice", "diced": "dice"}

FOODS_SPLITS = {
    'train': [
        'orange bell pepper',
        'block of cheese',
        'black pepper',
        'red hot pepper',
        'yellow bell pepper',
        'banana',
        'salt',
        'chicken leg',
        'cilantro',
        'white onion',
        'purple potato',
        'olive oil',
        'flour',
        'red onion',
        'yellow potato',
        'parsley',
        'red potato',
        'water',
        'pork chop',
        'red apple',
        'chicken wing',
        'carrot'
    ],
    'valid': [
        'vegetable oil',
        'green apple',
        'red tuna',
        'green bell pepper',
        'red bell pepper',
        'lettuce',
        'peanut oil',
        'chicken breast'
    ],
    'test': [
        'milk',
        'yellow onion',
        'yellow apple',
        'sugar',
        'egg',
        'green hot pepper',
        'white tuna',
        'tomato'
    ],
}

FOOD_PREPARATIONS_SPLITS = {
    'train': {
        'orange bell pepper': [('raw', 'chopped'), ('roasted', 'diced'), ('grilled', 'uncut'), ('raw', 'uncut'), ('raw', 'sliced'), ('grilled', 'sliced'), ('roasted', 'sliced'), ('fried', 'diced'), ('grilled', 'chopped')],
        'block of cheese': [('fried', 'diced'), ('fried', 'uncut'), ('grilled', 'chopped'), ('raw', 'chopped'), ('grilled', 'diced'), ('roasted', 'chopped'), ('grilled', 'sliced'), ('raw', 'uncut'), ('raw', 'sliced')],
        'black pepper': [('raw', 'uncut')],
        'red hot pepper': [('roasted', 'sliced'), ('fried', 'chopped'), ('roasted', 'uncut'), ('fried', 'sliced'), ('raw', 'sliced'), ('grilled', 'chopped'), ('fried', 'uncut'), ('raw', 'chopped'), ('grilled', 'sliced')],
        'yellow bell pepper': [('roasted', 'chopped'), ('grilled', 'sliced'), ('fried', 'sliced'), ('raw', 'diced'), ('roasted', 'diced'), ('fried', 'chopped'), ('roasted', 'uncut'), ('grilled', 'uncut'), ('fried', 'uncut')],
        'banana': [('grilled', 'diced'), ('fried', 'chopped'), ('grilled', 'chopped'), ('grilled', 'sliced'), ('fried', 'diced'), ('roasted', 'diced'), ('fried', 'sliced'), ('raw', 'sliced'), ('roasted', 'sliced')],
        'salt': [('raw', 'uncut')],
        'chicken leg': [('grilled', 'uncut')],
        'cilantro': [('raw', 'uncut'), ('raw', 'diced')],
        'white onion': [('grilled', 'uncut'), ('raw', 'chopped'), ('roasted', 'uncut'), ('roasted', 'sliced'), ('fried', 'diced'), ('raw', 'sliced'), ('grilled', 'chopped'), ('roasted', 'chopped'), ('roasted', 'diced')],
        'purple potato': [('roasted', 'sliced'), ('roasted', 'diced'), ('grilled', 'diced'), ('fried', 'chopped'), ('fried', 'sliced'), ('fried', 'diced'), ('roasted', 'uncut')],
        'olive oil': [('raw', 'uncut')],
        'flour': [('raw', 'uncut')],
        'red onion': [('raw', 'uncut'), ('roasted', 'uncut'), ('roasted', 'diced'), ('fried', 'sliced'), ('raw', 'sliced'), ('grilled', 'diced'), ('fried', 'diced'), ('raw', 'diced'), ('grilled', 'sliced')],
        'yellow potato': [('grilled', 'chopped'), ('grilled', 'sliced'), ('fried', 'diced'), ('fried', 'sliced'), ('fried', 'chopped'), ('roasted', 'chopped'), ('roasted', 'uncut')],
        'parsley': [('raw', 'diced'), ('raw', 'sliced')],
        'red potato': [('roasted', 'sliced'), ('grilled', 'chopped'), ('fried', 'uncut'), ('fried', 'chopped'), ('fried', 'diced'), ('fried', 'sliced'), ('roasted', 'diced')],
        'water': [('raw', 'uncut')],
        'pork chop': [('fried', 'sliced'), ('roasted', 'sliced'), ('grilled', 'uncut'), ('roasted', 'diced'), ('grilled', 'diced'), ('fried', 'uncut'), ('fried', 'chopped')],
        'red apple': [('grilled', 'sliced'), ('fried', 'diced'), ('roasted', 'sliced'), ('fried', 'sliced'), ('grilled', 'diced'), ('raw', 'uncut'), ('raw', 'sliced'), ('raw', 'diced'), ('roasted', 'chopped')],
        'chicken wing': [('grilled', 'uncut')],
        'carrot': [('roasted', 'sliced'), ('fried', 'chopped'), ('raw', 'uncut'), ('grilled', 'uncut'), ('roasted', 'uncut'), ('grilled', 'sliced'), ('raw', 'sliced'), ('fried', 'sliced'), ('raw', 'chopped')]},
    'valid': {
        'orange bell pepper': [('roasted', 'chopped'), ('fried', 'uncut'), ('fried', 'sliced'), ('raw', 'diced')],
        'block of cheese': [('roasted', 'diced'), ('grilled', 'uncut'), ('raw', 'diced'), ('roasted', 'sliced')],
        'black pepper': [('raw', 'uncut')],
        'red hot pepper': [('raw', 'diced'), ('roasted', 'chopped'), ('roasted', 'diced'), ('grilled', 'diced')],
        'yellow bell pepper': [('raw', 'chopped'), ('roasted', 'sliced'), ('fried', 'diced'), ('raw', 'sliced')],
        'banana': [('roasted', 'uncut'), ('grilled', 'uncut'), ('raw', 'diced'), ('roasted', 'chopped')],
        'salt': [('raw', 'uncut')],
        'chicken leg': [('fried', 'uncut')],
        'cilantro': [('raw', 'sliced')],
        'white onion': [('grilled', 'sliced'), ('raw', 'diced'), ('fried', 'chopped'), ('fried', 'uncut')],
        'purple potato': [('grilled', 'chopped'), ('grilled', 'uncut'), ('fried', 'uncut')],
        'olive oil': [('raw', 'uncut')],
        'flour': [('raw', 'uncut')],
        'red onion': [('roasted', 'chopped'), ('fried', 'chopped'), ('fried', 'uncut'), ('grilled', 'chopped')],
        'yellow potato': [('roasted', 'diced'), ('grilled', 'uncut'), ('grilled', 'diced')],
        'parsley': [('raw', 'uncut')],
        'red potato': [('grilled', 'diced'), ('grilled', 'sliced'), ('roasted', 'chopped')],
        'water': [('raw', 'uncut')],
        'pork chop': [('fried', 'diced'), ('roasted', 'chopped'), ('roasted', 'uncut')],
        'red apple': [('raw', 'chopped'), ('roasted', 'diced'), ('grilled', 'uncut'), ('fried', 'chopped')],
        'chicken wing': [('roasted', 'uncut')],
        'carrot': [('grilled', 'chopped'), ('fried', 'uncut'), ('roasted', 'chopped'), ('roasted', 'diced')]},
    'test': {
        'orange bell pepper': [('roasted', 'uncut'), ('fried', 'chopped'), ('grilled', 'diced')],
        'block of cheese': [('fried', 'chopped'), ('roasted', 'uncut'), ('fried', 'sliced')],
        'black pepper': [('raw', 'uncut')],
        'red hot pepper': [('raw', 'uncut'), ('grilled', 'uncut'), ('fried', 'diced')],
        'yellow bell pepper': [('grilled', 'chopped'), ('raw', 'uncut'), ('grilled', 'diced')],
        'banana': [('raw', 'chopped'), ('fried', 'uncut'), ('raw', 'uncut')],
        'salt': [('raw', 'uncut')],
        'chicken leg': [('roasted', 'uncut')],
        'cilantro': [('raw', 'chopped')],
        'white onion': [('raw', 'uncut'), ('fried', 'sliced'), ('grilled', 'diced')],
        'purple potato': [('grilled', 'sliced'), ('roasted', 'chopped')],
        'olive oil': [('raw', 'uncut')],
        'flour': [('raw', 'uncut')],
        'red onion': [('raw', 'chopped'), ('grilled', 'uncut'), ('roasted', 'sliced')],
        'yellow potato': [('fried', 'uncut'), ('roasted', 'sliced')],
        'parsley': [('raw', 'chopped')],
        'red potato': [('grilled', 'uncut'), ('roasted', 'uncut')],
        'water': [('raw', 'uncut')],
        'pork chop': [('grilled', 'sliced'), ('grilled', 'chopped')],
        'red apple': [('fried', 'uncut'), ('roasted', 'uncut'), ('grilled', 'chopped')],
        'chicken wing': [('fried', 'uncut')],
        'carrot': [('raw', 'diced'), ('grilled', 'diced'), ('fried', 'diced')]
  }
}

FOODS_COMPACT = {
    "egg" : {
        "properties": ["inedible", "cookable", "needs_cooking"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "milk" : {
        "indefinite": "some",
        "properties": ["drinkable", "inedible"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "water" : {
        "indefinite": "some",
        "properties": ["drinkable", "inedible"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "cooking oil" : {
        "names": ["vegetable oil", "peanut oil", "olive oil"],
        "indefinite": "some",
        "properties": ["inedible"],
        "locations": ["pantry.shelf", "supermarket.showcase"],
    },
    "chicken wing" : {
        "properties": ["inedible", "cookable", "needs_cooking"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "chicken leg" : {
        "properties": ["inedible", "cookable", "needs_cooking"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "chicken breast" : {
        "properties": ["inedible", "cookable", "needs_cooking"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "pork chop" : {
        "properties": ["inedible", "cookable", "needs_cooking", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "tuna" : {
        "names": ["red tuna", "white tuna"],
        "properties": ["inedible", "cookable", "needs_cooking", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "carrot" : {
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "garden"],
    },
    "onion" : {
        "names": ["red onion", "white onion", "yellow onion"],
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "garden"],
    },
    "lettuce" : {
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "garden"],
    },
    "potato" : {
        "names": ["red potato", "yellow potato", "purple potato"],
        "properties": ["inedible", "cookable", "needs_cooking", "cuttable", "uncut"],
        "locations": ["kitchen.counter", "garden"],
    },
    "apple" : {
        "names": ["red apple", "yellow apple", "green apple"],
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.counter", "garden"],
    },
    "banana" : {
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.counter", "garden"],
    },
    "tomato" : {
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.counter", "garden"],
    },
    "hot pepper" : {
        "names": ["red hot pepper", "green hot pepper"],
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.counter", "garden"],
    },
    "bell pepper" : {
        "names": ["red bell pepper", "yellow bell pepper", "green bell pepper", "orange bell pepper"],
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "garden"],
    },
    "black pepper" : {
        "properties": ["edible"],
        "locations": ["pantry.shelf", "supermarket.showcase"],
    },
    "flour" : {
        "properties": ["edible"],
        "locations": ["pantry.shelf", "supermarket.showcase"],
    },
    "salt" : {
        "properties": ["edible"],
        "locations": ["pantry.shelf", "supermarket.showcase"],
    },
    "sugar" : {
        "properties": ["edible"],
        "locations": ["pantry.shelf", "supermarket.showcase"],
    },
    "block of cheese" : {
        "properties": ["edible", "cookable", "raw", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "supermarket.showcase"],
    },
    "cilantro" : {
        "properties": ["edible", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "garden"],
    },
    "parsley" : {
        "properties": ["edible", "cuttable", "uncut"],
        "locations": ["kitchen.fridge", "garden"],
    }
}

FOODS = {}
for k, v in FOODS_COMPACT.items():
    if "names" in v:
        for name in v["names"]:
            FOODS[name] = dict(v)
            del FOODS[name]["names"]
    else:
        FOODS[k] = v


ENTITIES = {
    "cookbook": {
        "type": "o",
        "names": ["cookbook", "recipe book"],
        "adjs": ["interesting"],
        "locations": ["kitchen.counter", "kitchen.table"],
        "properties": [],
        "desc": [None],
    },
    "knife": {
        "type": "o",
        "names": ["knife"],
        "adjs": ["sharp"],
        "locations": ["kitchen.counter", "kitchen.table"],
        "properties": ["sharp"],
        "desc": [None],
    },

    # Kitchen
    "fridge": {
        "type": "c",
        "names": ["fridge", "refrigerator"],
        "adjs": ["conventional"],
        "locations": ["kitchen"],
        "properties": ["closed"],
        "desc": [None],
    },
    "counter": {
        "type": "s",
        "names": ["counter"],
        "adjs": ["vast"],
        "locations": ["kitchen"],
        "properties": [],
        "desc": [None],
    },
    "table": {
        "type": "s",
        "names": ["table", "kitchen island"],
        "adjs": ["massive"],
        "locations": ["kitchen"],
        "properties": [],
        "desc": [None],
    },
    "stove": {
        "type": "stove",
        "names": ["stove"],
        "adjs": ["conventional"],
        "locations": ["kitchen"],
        "properties": [],
        "desc": ["Useful for frying things."],
    },
    "oven": {
        "type": "oven",
        "names": ["oven"],
        "adjs": ["conventional"],
        "locations": ["kitchen"],
        "properties": [],
        "desc": ["Useful for roasting things."],
    },

    # Pantry
    "shelf": {
        "type": "s",
        "names": ["shelf"],
        "adjs": ["wooden"],
        "locations": ["pantry"],
        "properties": [],
        "desc": [None],
    },

    # Backyard
    "BBQ": {
        "type": "toaster",
        "names": ["BBQ"],
        "adjs": ["recent"],
        "locations": ["backyard"],
        "properties": [],
        "desc": ["Useful for grilling things."],
    },
    "patio table": {
        "type": "s",
        "names": ["patio table"],
        "adjs": ["stylish"],
        "locations": ["backyard"],
        "properties": [],
        "desc": [None],
    },
    "patio chair": {
        "type": "s",
        "names": ["patio chair"],
        "adjs": ["stylish"],
        "locations": ["backyard"],
        "properties": [],
        "desc": [None],
    },

    # Supermarket
    "showcase": {
        "type": "s",
        "names": ["showcase"],
        "adjs": ["metallic"],
        "locations": ["supermarket"],
        "properties": [],
        "desc": [None],
    },

    # Livingroom
    "sofa": {
        "type": "s",
        "names": ["sofa", "couch"],
        "adjs": ["comfy"],
        "locations": ["livingroom"],
        "properties": [],
        "desc": [None],
    },
    "sofa": {
        "type": "s",
        "names": ["sofa", "couch"],
        "adjs": ["comfy"],
        "locations": ["livingroom"],
        "properties": [],
        "desc": [None],
    },

    # Bedroom
    "bed": {
        "type": "s",
        "names": ["bed"],
        "adjs": ["large"],
        "locations": ["bedroom"],
        "properties": [],
        "desc": [None],
    },

    # Bathroom
    "toilet": {
        "type": "s",
        "names": ["toilet"],
        "adjs": ["white"],
        "locations": ["bathroom"],
        "properties": [],
        "desc": [None],
    },
    # "bath": {
    #     "type": "unclosable-container",
    #     "names": ["bathtub"],
    #     "adjs": ["white"],
    #     "locations": ["bathroom"],
    #     "properties": [],
    #     "desc": [None],
    # },

    # Shed
    "workbench": {
        "type": "s",
        "names": ["workbench"],
        "adjs": ["wooden"],
        "locations": ["shed"],
        "properties": [],
        "desc": [None],
    },
    "toolbox": {
        "type": "c",
        "names": ["toolbox"],
        "adjs": ["metallic"],
        "locations": ["shed"],
        "properties": ["closed"],
        "desc": [None],
    },

}

NEIGHBORS = {
    "kitchen": ["livingroom", "backyard", "corridor", "pantry"],
    "pantry": ["kitchen"],
    "livingroom": ["kitchen", "bedroom", "driveway", "corridor"],
    "bathroom": ["corridor"],
    "bedroom": ["livingroom", "corridor"],
    "backyard": ["kitchen", "garden", "shed", "corridor"],
    "garden": ["backyard"],
    "shed": ["backyard"],
    "driveway": ["livingroom", "street", "corridor"],
    "street": ["driveway", "supermarket"],
    "corridor": ["livingroom", "kitchen", "bedroom", "bathroom", "driveway", "backyard"],
    "supermarket": ["street"],
}

ROOMS = [
    ["kitchen"],
    ["pantry", "livingroom", "corridor", "bedroom", "bathroom"],
    ["shed", "garden", "backyard"],
    ["driveway", "street", "supermarket"]
]

DOORS = [
    {
        "path": ("pantry", "kitchen"),
        "names": ["frosted-glass door", "plain door"],
    },
    {
        "path": ("kitchen", "backyard"),
        "names": ["sliding patio door", "patio door", "screen door"],
    },
    {
        "path": ("corridor", "backyard"),
        "names": ["sliding patio door", "patio door", "screen door"],
    },
    {
        "path": ("backyard", "shed"),
        "names": ["barn door", "wooden door"],
    },
    {
        "path": ("livingroom", "driveway"),
        "names": ["front door", "fiberglass door"],
    },
    {
        "path": ("corridor", "driveway"),
        "names": ["front door", "fiberglass door"],
    },
    {
        "path": ("supermarket", "street"),
        "names": ["sliding door", "commercial glass door"],
    },
]

def pick_name(M, names, rng):
    names = list(names)
    rng.shuffle(names)
    for name in names:
        if M.find_by_name(name) is None:
            return name

    assert False
    return None


def get_food_preparations(foods):
    food_preparations = {}
    for f in foods:
        v = FOODS[f]
        cookings = ["raw"]
        if "cookable" in v["properties"]:
            cookings = ["grilled", "fried", "roasted"]
            if "needs_cooking" not in v["properties"]:
                cookings.append("raw")

        cuttings = ["uncut"]
        if "cuttable" in v["properties"]:
            cuttings = ["uncut", "chopped", "sliced", "diced"]

        food_preparations[f] = list(itertools.product(cookings, cuttings))

    return food_preparations


def pick_location(M, locations, rng):
    locations = list(locations)
    rng.shuffle(locations)
    for location in locations:
        holder_name = location.split(".")[-1]
        holder = M.find_by_name(holder_name)
        if holder:
            return holder
        # else:
        #     print("Can't find {}".format(location))

    return None


def place_food(M, name, rng, place_it=True):
    holder = pick_location(M, FOODS[name]["locations"], rng)
    if holder is None and place_it:
        return None

    food = M.new(type=FOODS[name].get("type", "f"), name=name)
    food.infos.adj = ""
    food.infos.noun = name
    if "indefinite" in FOODS[name]:
        food.infos.indefinite = FOODS[name]["indefinite"]

    for property_ in FOODS[name]["properties"]:
        food.add_property(property_)

    if place_it:
        holder.add(food)

    return food


def place_foods(M, foods, rng):
    entities = []
    for name in foods:
        food = place_food(M, name, rng)
        if food:
            entities.append(food)

    return entities


def place_random_foods(M, nb_foods, rng, allowed_foods=FOODS):
    seen = set(food.name for food in M.findall(type="f"))
    foods = [name for name in allowed_foods if name not in seen]
    rng.shuffle(foods)
    entities = []
    for food in foods:
        if len(entities) >= nb_foods:
            break

        entities += place_foods(M, [food], rng)

    return entities


def place_entity(M, name, rng):
    holder = pick_location(M, ENTITIES[name]["locations"], rng)
    if holder is None:
        return None  # Nowhere to place it.

    entity = M.new(type=ENTITIES[name]["type"], name=name)
    entity.infos.adj = ENTITIES[name]["adjs"][0]
    entity.infos.noun = name
    entity.infos.desc = ENTITIES[name]["desc"][0]
    for property_ in ENTITIES[name]["properties"]:
        entity.add_property(property_)

    holder.add(entity)
    return entity


def place_entities(M, names, rng):
    return [place_entity(M, name, rng) for name in names]


def place_random_furnitures(M, nb_furnitures, rng):
    furnitures = [k for k, v in ENTITIES.items() if v["type"] not in ["o", "f"]]
    # Skip existing furnitures.
    furnitures = [furniture for furniture in furnitures if not M.find_by_name(furniture)]
    rng.shuffle(furnitures)
    return place_entities(M, furnitures[:nb_furnitures], rng)


def move(M, start, end):
    path = nx.algorithms.shortest_path(M.G, start.id, end.id)
    commands = []
    current_room = start
    for node in path[1:]:
        previous_room = current_room
        direction, current_room = [(exit.direction, exit.dest.src) for exit in previous_room.exits.values()
                                   if exit.dest and exit.dest.src.id == node][0]

        path = M.find_path(previous_room, current_room)
        if path.door:
            commands.append("open {}".format(path.door.name))

        commands.append("go {}".format(direction))

    return commands


def make_game(skills: Dict["str", Union[bool, int]], options: GameOptions, split: str = "",
              neverending: bool = False) -> textworld.Game:
    """ Make a Cooking game.
    Arguments:
        skills:
            Skills to test in this game (see notes).
        options:
            For customizing the game generation (see
            :py:class:`textworld.GameOptions <textworld.generator.game.GameOptions>`
            for the list of available options).
        split:
            Control which foods can be used. Can either be 'train', 'valid', 'test'.
            Default: foods from all dataset splits can be used.
        neverending:
            If `True` the generate game won't have any quests.
    Returns:
        Generated game.
    Notes:
        The required skills are:
        * recipe{1,2,3} : Number of ingredients in the recipe.
        The optional skills that can be combined are:
        * take{1,2,3} : Number of ingredients to fetch. It must be less
          or equal to the value of the `recipe` skill.
        * open : Whether containers/doors need to be opened.
        * cook : Whether some ingredients need to be cooked.
        * cut : Whether some ingredients need to be cut.
        * drop : Whether the player's inventory has limited capacity.
        * go{1,6,9,12} : Number of locations in the game.
    """
    rngs = options.rngs
    rng_map = rngs['map']
    rng_objects = rngs['objects']
    rng_grammar = rngs['grammar']
    rng_quest = rngs['quest']

    allowed_foods = list(FOODS)
    allowed_food_preparations = get_food_preparations(list(FOODS))
    if split == "train":
        allowed_foods = list(FOODS_SPLITS['train'])
        allowed_food_preparations = dict(FOOD_PREPARATIONS_SPLITS['train'])
    elif split == "valid":
        allowed_foods = list(FOODS_SPLITS['valid'])
        allowed_food_preparations = get_food_preparations(FOODS_SPLITS['valid'])
        # Also add food from the training set but with different preparations.
        allowed_foods += [f for f in FOODS if f in FOODS_SPLITS['train']]
        allowed_food_preparations.update(dict(FOOD_PREPARATIONS_SPLITS['valid']))
    elif split == "test":
        allowed_foods = list(FOODS_SPLITS['test'])
        allowed_food_preparations = get_food_preparations(FOODS_SPLITS['test'])
        # Also add food from the training set but with different preparations.
        allowed_foods += [f for f in FOODS if f in FOODS_SPLITS['train']]
        allowed_food_preparations.update(dict(FOOD_PREPARATIONS_SPLITS['test']))

    M = textworld.GameMaker()

    recipe = M.new(type='RECIPE', name='')
    meal = M.new(type='meal', name='meal')
    M.add_fact("out", meal, recipe)
    meal.add_property("edible")
    M.nowhere.append(recipe)  # Out of play object.
    M.nowhere.append(meal)  # Out of play object.

    options.nb_rooms = skills.get("go", 1)
    if options.nb_rooms == 1:
        rooms_to_place = ROOMS[:1]
    elif options.nb_rooms == 6:
        rooms_to_place = ROOMS[:2]
    elif options.nb_rooms == 9:
        rooms_to_place = ROOMS[:3]
    elif options.nb_rooms == 12:
        rooms_to_place = ROOMS[:4]
    else:
        raise ValueError("Cooking games can only have {1, 6, 9, 12} rooms.")

    G = make_graph_world(rng_map, rooms_to_place, NEIGHBORS, size=(5, 5))
    rooms = M.import_graph(G)

    # Add doors
    for infos in DOORS:
        room1 = M.find_by_name(infos["path"][0])
        room2 = M.find_by_name(infos["path"][1])
        if room1 is None or room2 is None:
            continue  # This door doesn't exist in this world.

        path = M.find_path(room1, room2)
        if path:
            assert path.door is None
            name = pick_name(M, infos["names"], rng_objects)
            door = M.new_door(path, name)
            door.add_property("closed")

    # Find kitchen.
    kitchen = M.find_by_name("kitchen")

    # The following predicates will be used to force the "prepare meal"
    # command to happen in the kitchen.
    M.add_fact("cooking_location", kitchen, recipe)

    # Place some default furnitures.
    place_entities(M, ["table", "stove", "oven", "counter", "fridge", "BBQ", "shelf", "showcase"], rng_objects)

    # Place some random furnitures.
    nb_furnitures = rng_objects.randint(len(rooms), len(ENTITIES) + 1)
    place_random_furnitures(M, nb_furnitures, rng_objects)

    # Place the cookbook and knife somewhere.
    cookbook = place_entity(M, "cookbook", rng_objects)
    cookbook.infos.synonyms = ["recipe"]
    if rng_objects.rand() > 0.5 or skills.get("cut"):
        knife = place_entity(M, "knife", rng_objects)

    start_room = rng_map.choice(M.rooms)
    M.set_player(start_room)

    M.grammar = textworld.generator.make_grammar(options.grammar, rng=rng_grammar)

    # Remove every food preparation with grilled, if there is no BBQ.
    if M.find_by_name("BBQ") is None:
        for name, food_preparations in allowed_food_preparations.items():
            allowed_food_preparations[name] = [food_preparation for food_preparation in food_preparations
                                               if "grilled" not in food_preparation]

        # Disallow food with an empty preparation list.
        allowed_foods = [name for name in allowed_foods if allowed_food_preparations[name]]

    # Decide which ingredients are needed.
    nb_ingredients = skills.get("recipe", 1)
    assert nb_ingredients > 0 and nb_ingredients <= 5, "recipe must have {1,2,3,4,5} ingredients."
    ingredient_foods = place_random_foods(M, nb_ingredients, rng_quest, allowed_foods)

    # Sort by name (to help differentiate unique recipes).
    ingredient_foods = sorted(ingredient_foods, key=lambda f: f.name)

    # Decide on how the ingredients should be processed.
    ingredients = []
    for i, food in enumerate(ingredient_foods):
        food_preparations = allowed_food_preparations[food.name]
        idx = rng_quest.randint(0, len(food_preparations))
        type_of_cooking, type_of_cutting = food_preparations[idx]

        ingredient = M.new(type="ingredient", name="")
        food.add_property("ingredient_{}".format(i + 1))
        M.add_fact("base", food, ingredient)
        M.add_fact(type_of_cutting, ingredient)
        M.add_fact(type_of_cooking, ingredient)
        M.add_fact("in", ingredient, recipe)
        M.nowhere.append(ingredient)
        ingredients.append((food, type_of_cooking, type_of_cutting))

    # Move ingredients in the player's inventory according to the `take` skill.
    nb_ingredients_already_in_inventory = nb_ingredients - skills.get("take", 0)
    shuffled_ingredients = list(ingredient_foods)
    rng_quest.shuffle(shuffled_ingredients)
    for ingredient in shuffled_ingredients[:nb_ingredients_already_in_inventory]:
        M.move(ingredient, M.inventory)

    # Compute inventory capacity.
    inventory_limit = 10  # More than enough.
    if skills.get("drop"):
        inventory_limit = nb_ingredients
        if nb_ingredients == 1 and skills.get("cut"):
            inventory_limit += 1  # So we can hold the knife along with the ingredient.

    # Add distractors for each ingredient.
    def _place_one_distractor(candidates, ingredient):
        rng_objects.shuffle(candidates)
        for food_name in candidates:
            distractor = M.find_by_name(food_name)
            if distractor:
                if distractor.parent == ingredient.parent:
                    break  # That object already exists and is considered as a distractor.

                continue  # That object already exists. Can't used it as distractor.

            # Place the distractor in the same "container" as the ingredient.
            distractor = place_food(M, food_name, rng_objects, place_it=False)
            ingredient.parent.add(distractor)
            break

    for ingredient in ingredient_foods:
        if ingredient.parent == M.inventory and nb_ingredients_already_in_inventory >= inventory_limit:
            # If ingredient is in the inventory but inventory is full, do not add distractors.
            continue

        splits = ingredient.name.split()
        if len(splits) == 1:
            continue  # No distractors.

        prefix, suffix = splits[0], splits[-1]
        same_prefix_list = [f for f in allowed_foods if f.startswith(prefix) if f != ingredient.name]
        same_suffix_list = [f for f in allowed_foods if f.endswith(suffix) if f != ingredient.name]

        if same_prefix_list:
            _place_one_distractor(same_prefix_list, ingredient)

        if same_suffix_list:
            _place_one_distractor(same_suffix_list, ingredient)

    # Add distractors foods. The amount is drawn from N(nb_ingredients, 3).
    nb_distractors = max(0, int(rng_objects.randn(1) * 3 + nb_ingredients))
    distractors = place_random_foods(M, nb_distractors, rng_objects, allowed_foods)

    # Depending on the skills and how the ingredient should be processed
    # we change the predicates of the food objects accordingly.
    for food, type_of_cooking, type_of_cutting in ingredients:
        if not skills.get("cook"):  # Food should already be cooked accordingly.
            food.add_property(type_of_cooking)
            food.add_property("cooked")
            if food.has_property("inedible"):
                food.add_property("edible")
                food.remove_property("inedible")
            if food.has_property("raw"):
                food.remove_property("raw")
            if food.has_property("needs_cooking"):
                food.remove_property("needs_cooking")

        if not skills.get("cut"):  # Food should already be cut accordingly.
            food.add_property(type_of_cutting)
            food.remove_property("uncut")

    if not skills.get("open"):
        for entity in M._entities.values():
            if entity.has_property("closed"):
                entity.remove_property("closed")
                entity.add_property("open")

    walkthrough = []
    if not neverending:
        # Build TextWorld quests.
        quests = []
        consumed_ingredient_events = []
        for i, ingredient in enumerate(ingredients):
            ingredient_consumed = Event(conditions={M.new_fact("consumed", ingredient[0])})
            consumed_ingredient_events.append(ingredient_consumed)
            ingredient_burned = Event(conditions={M.new_fact("burned", ingredient[0])})
            quests.append(Quest(win_events=[], fail_events=[ingredient_burned]))

            if ingredient[0] not in M.inventory:
                holding_ingredient = Event(conditions={M.new_fact("in", ingredient[0], M.inventory)})
                quests.append(Quest(win_events=[holding_ingredient]))

            win_events = []
            if ingredient[1] != TYPES_OF_COOKING[0] and not ingredient[0].has_property(ingredient[1]):
                win_events += [Event(conditions={M.new_fact(ingredient[1], ingredient[0])})]

            fail_events = [Event(conditions={M.new_fact(t, ingredient[0])})
                           for t in set(TYPES_OF_COOKING[1:]) - {ingredient[1]}]  # Wrong cooking.

            quests.append(Quest(win_events=win_events, fail_events=[ingredient_consumed] + fail_events))

            win_events = []
            if ingredient[2] != TYPES_OF_CUTTING[0] and not ingredient[0].has_property(ingredient[2]):
                win_events += [Event(conditions={M.new_fact(ingredient[2], ingredient[0])})]

            fail_events = [Event(conditions={M.new_fact(t, ingredient[0])})
                        for t in set(TYPES_OF_CUTTING[1:]) - {ingredient[2]}]  # Wrong cutting.

            quests.append(Quest(win_events=win_events, fail_events=[ingredient_consumed] + fail_events))

        holding_meal = Event(conditions={M.new_fact("in", meal, M.inventory)})
        quests.append(Quest(win_events=[holding_meal], fail_events=consumed_ingredient_events))

        meal_burned = Event(conditions={M.new_fact("burned", meal)})
        meal_consumed = Event(conditions={M.new_fact("consumed", meal)})
        quests.append(Quest(win_events=[meal_consumed], fail_events=[meal_burned]))

        M.quests = quests

        M.compute_graph()  # Needed by the move(...) function called below.

        # Build walkthrough.
        current_room = start_room
        walkthrough = []

        # Start by checking the inventory.
        walkthrough.append("inventory")

        # 0. Find the kitchen and read the cookbook.
        walkthrough += move(M, current_room, kitchen)
        current_room = kitchen
        walkthrough.append("examine cookbook")

        # 1. Drop unneeded objects.
        for entity in M.inventory.content:
            if entity not in ingredient_foods:
                walkthrough.append("drop {}".format(entity.name))


        # 2. Collect the ingredients.
        for food, type_of_cooking, type_of_cutting in ingredients:
            if food.parent == M.inventory:
                continue

            food_room = food.parent.parent if food.parent.parent else food.parent
            walkthrough += move(M, current_room, food_room)

            if food.parent.has_property("closed"):
                walkthrough.append("open {}".format(food.parent.name))

            if food.parent == food_room:
                walkthrough.append("take {}".format(food.name))
            else:
                walkthrough.append("take {} from {}".format(food.name, food.parent.name))

            current_room = food_room

        # 3. Go back to the kitchen.
        walkthrough += move(M, current_room, kitchen)

        # 4. Process ingredients (cook).
        if skills.get("cook"):
            for food, type_of_cooking, _ in ingredients:
                if type_of_cooking == "fried":
                    stove = M.find_by_name("stove")
                    walkthrough.append("cook {} with {}".format(food.name, stove.name))
                elif type_of_cooking == "roasted":
                    oven = M.find_by_name("oven")
                    walkthrough.append("cook {} with {}".format(food.name, oven.name))
                elif type_of_cooking == "grilled":
                    toaster = M.find_by_name("BBQ")
                    # 3.a move to the backyard.
                    walkthrough += move(M, kitchen, toaster.parent)
                    # 3.b grill the food.
                    walkthrough.append("cook {} with {}".format(food.name, toaster.name))
                    # 3.c move back to the kitchen.
                    walkthrough += move(M, toaster.parent, kitchen)

        # 5. Process ingredients (cut).
        if skills.get("cut"):
            free_up_space = skills.get("drop") and not len(ingredients) == 1
            knife = M.find_by_name("knife")
            if knife:
                knife_location = knife.parent.name
                knife_on_the_floor = knife_location == "kitchen"
                for i, (food, _, type_of_cutting) in enumerate(ingredients):
                    if type_of_cutting == "uncut":
                        continue

                    if free_up_space:
                        ingredient_to_drop = ingredients[(i + 1) % len(ingredients)][0]
                        walkthrough.append("drop {}".format(ingredient_to_drop.name))

                    # Assume knife is reachable.
                    if knife_on_the_floor:
                        walkthrough.append("take {}".format(knife.name))
                    else:
                        walkthrough.append("take {} from {}".format(knife.name, knife_location))

                    if type_of_cutting == "chopped":
                        walkthrough.append("chop {} with {}".format(food.name, knife.name))
                    elif type_of_cutting == "sliced":
                        walkthrough.append("slice {} with {}".format(food.name, knife.name))
                    elif type_of_cutting == "diced":
                        walkthrough.append("dice {} with {}".format(food.name, knife.name))

                    walkthrough.append("drop {}".format(knife.name))
                    knife_on_the_floor = True
                    if free_up_space:
                        walkthrough.append("take {}".format(ingredient_to_drop.name))

        # 6. Prepare and eat meal.
        walkthrough.append("prepare meal")
        walkthrough.append("eat meal")

    cookbook_desc = "You open the copy of 'Cooking: A Modern Approach (3rd Ed.)' and start reading:\n"
    recipe = textwrap.dedent(
    """
    Recipe #1
    ---------
    Gather all following ingredients and follow the directions to prepare this tasty meal.
    Ingredients:
      {ingredients}
    Directions:
      {directions}
    """)
    recipe_ingredients = "\n  ".join(ingredient[0].name for ingredient in ingredients)

    recipe_directions = []
    for ingredient in ingredients:
        cutting_verb = TYPES_OF_CUTTING_VERBS.get(ingredient[2])
        if cutting_verb:
            recipe_directions.append(cutting_verb + " the " + ingredient[0].name)

        cooking_verb = TYPES_OF_COOKING_VERBS.get(ingredient[1])
        if cooking_verb:
            recipe_directions.append(cooking_verb + " the " + ingredient[0].name)

    recipe_directions.append("prepare meal")
    recipe_directions = "\n  ".join(recipe_directions)
    recipe = recipe.format(ingredients=recipe_ingredients, directions=recipe_directions)
    cookbook.infos.desc = cookbook_desc + recipe

    # Limit capacity of the inventory.
    for i in range(inventory_limit):
        slot = M.new(type="slot", name="")
        if i < len(M.inventory.content):
            slot.add_property("used")
        else:
            slot.add_property("free")

        M.nowhere.append(slot)

    # Sanity checks:
    for entity in M._entities.values():
        if entity.type in ["c", "d"]:
            if not (entity.has_property("closed") or
                    entity.has_property("open") or
                    entity.has_property("locked")):
                raise ValueError("Forgot to add closed/locked/open property for '{}'.".format(entity.name))

    #pprint(metadata)
    #print(". ".join(walkthrough))
    #img = M.render()
    #img.save("tmp.png")

    #M.render(True)
    # M.test()
    game = M.build()
    #game.main_quest = M.new_quest_using_commands(walkthrough)
    # print(". ".join(game.main_quest.commands))

    # Collect infos about this game.
    metadata = {
        "seeds": options.seeds,
        "goal": cookbook.infos.desc,
        "ingredients": [(food.name, cooking, cutting) for food, cooking, cutting in ingredients],
        "skills": skills,
        "entities": [e.name for e in M._entities.values() if e.name],
        "nb_distractors": nb_distractors,
        "walkthrough": walkthrough,
        "max_score": sum(quest.reward for quest in game.quests),
    }

    game.extras["recipe"] = recipe
    game.extras["walkthrough"] = walkthrough
    objective = ("You are hungry! Let's cook a delicious meal. Check the cookbook"
                 " in the kitchen for the recipe. Once done, enjoy your meal!")
    game.objective = objective

    game.metadata = metadata
    skills_uuid = "+".join("{}{}".format(k, "" if skills[k] is True else skills[k]) for k in SKILLS if k in skills)
    uuid = "tw-cooking-{specs}-{seeds}"
    uuid = uuid.format(specs=skills_uuid,
                       seeds=encode_seeds([options.seeds[k] for k in sorted(options.seeds)]))
    game.metadata["uuid"] = uuid
    return game


def make(settings: str, options: Optional[GameOptions] = None) -> textworld.Game:
    """ Make a Cooking game of the desired difficulty settings.
    Arguments:
        settings:
            Skills used in the game (see notes). Expected pattern: skill[+skill ...].
        options:
            For customizing the game generation (see
            :py:class:`textworld.GameOptions <textworld.generator.game.GameOptions>`
            for the list of available options).
    Returns:
        Generated game.
    Notes:
        The required skills are:
        * recipe{1,2,3} : Number of ingredients in the recipe.
        The optional skills that can be combined are:
        * take{1,2,3} : Number of ingredients to fetch. It must be less
          or equal to the value of the `recipe` skill.
        * open : Whether containers/doors need to be opened.
        * cook : Whether some ingredients need to be cooked.
        * cut : Whether some ingredients need to be cut.
        * drop : Whether the player's inventory has limited capacity.
        * go{1,6,9,12} : Number of locations in the game.
    """
    options or GameOptions()

    def _parse(skill):
        match = re.match(r"([^0-9]+)([0-9]+)", skill)
        if match:
            return match.group(1), int(match.group(2))

        return skill, True

    skills = dict([_parse(skill) for skill in settings.split("+")])
    split = ""
    if "train" in skills:
        split += "train"
        del skills["train"]
    elif "valid" in skills:
        split += "valid"
        del skills["valid"]
    elif "test" in skills:
        split += "test"
        del skills["test"]

    neverending = "noquest" in skills

    assert split in {'', 'train', 'valid', 'test'}

    return make_game(skills, options, split, neverending)


register(name="cooking",
         make=make,
         settings="recipe{1,2,3}+take{1,2,3}+open+cook+cut+drop+go{1,6,9,12}")


def play(agent, path, max_step=50, nb_episodes=10, verbose=True):
    infos_to_request = agent.infos_to_request
    infos_to_request.max_score = True  # Needed to normalize the scores.

    gamefiles = [path]
    if os.path.isdir(path):
        gamefiles = glob(os.path.join(path, "*.ulx"))

    env_id = textworld.gym.register_games(gamefiles,
                                          request_infos=infos_to_request,
                                          max_episode_steps=max_step)
    env = gym.make(env_id)  # Create a Gym environment to play the text game.
    if verbose:
        if os.path.isdir(path):
            print(os.path.dirname(path), end="")
        else:
            print(os.path.basename(path), end="")

    # Collect some statistics: nb_steps, final reward.
    avg_moves, avg_scores, avg_norm_scores = [], [], []
    for no_episode in range(nb_episodes):
        obs, infos = env.reset()  # Start new episode.

        score = 0
        done = False
        nb_moves = 0
        while not done:
            command = agent.act(obs, score, done, infos)
            obs, score, done, infos = env.step(command)
            nb_moves += 1

        agent.act(obs, score, done, infos)  # Let the agent know the game is done.

        if verbose:
            print(".", end="")
        avg_moves.append(nb_moves)
        avg_scores.append(score)
        avg_norm_scores.append(score / infos["max_score"])

    env.close()
    msg = "  \tavg. steps: {:5.1f}; avg. score: {:4.1f} / {}."
    if verbose:
        if os.path.isdir(path):
            print(msg.format(np.mean(avg_moves), np.mean(avg_norm_scores), 1))
        else:
            print(msg.format(np.mean(avg_moves), np.mean(avg_scores), infos["max_score"]))


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class CommandScorer(nn.Module):
    def __init__(self, input_size, hidden_size):
        super(CommandScorer, self).__init__()
        torch.manual_seed(42)  # For reproducibility
        self.embedding = nn.Embedding(input_size, hidden_size)
        self.encoder_gru = nn.GRU(hidden_size, hidden_size)
        self.cmd_encoder_gru = nn.GRU(hidden_size, hidden_size)
        self.state_gru = nn.GRU(hidden_size, hidden_size)
        self.hidden_size = hidden_size
        self.state_hidden = torch.zeros(1, 1, hidden_size, device=device)
        self.critic = nn.Linear(hidden_size, 1)
        self.att_cmd = nn.Linear(hidden_size * 2, 1)

    def forward(self, obs, commands, **kwargs):
        input_length = obs.size(0)
        batch_size = obs.size(1)
        nb_cmds = commands.size(1)

        embedded = self.embedding(obs)
        encoder_output, encoder_hidden = self.encoder_gru(embedded)
        state_output, state_hidden = self.state_gru(encoder_hidden, self.state_hidden)
        self.state_hidden = state_hidden
        value = self.critic(state_output)

        # Attention network over the commands.
        cmds_embedding = self.embedding.forward(commands)
        _, cmds_encoding_last_states = self.cmd_encoder_gru.forward(cmds_embedding)  # 1 x cmds x hidden

        # Same observed state for all commands.
        cmd_selector_input = torch.stack([state_hidden] * nb_cmds, 2)  # 1 x batch x cmds x hidden

        # Same command choices for the whole batch.
        cmds_encoding_last_states = torch.stack([cmds_encoding_last_states] * batch_size,
                                                1)  # 1 x batch x cmds x hidden

        # Concatenate the observed state and command encodings.
        cmd_selector_input = torch.cat([cmd_selector_input, cmds_encoding_last_states], dim=-1)

        # Compute one score per command.
        scores = F.relu(self.att_cmd(cmd_selector_input)).squeeze(-1)  # 1 x Batch x cmds

        probs = F.softmax(scores, dim=2)  # 1 x Batch x cmds
        index = probs[0].multinomial(num_samples=1).unsqueeze(0)  # 1 x batch x indx
        return scores, index, value

    def reset_hidden(self, batch_size):
        self.state_hidden = torch.zeros(1, batch_size, self.hidden_size, device=device)


class NeuralAgent:
    """ Simple Neural Agent for playing TextWorld games. """
    MAX_VOCAB_SIZE = 1000
    UPDATE_FREQUENCY = 10
    LOG_FREQUENCY = 1000
    GAMMA = 0.9

    def __init__(self) -> None:
        self._initialized = False
        self._epsiode_has_started = False
        self.id2word = ["<PAD>", "<UNK>"]
        self.word2id = {w: i for i, w in enumerate(self.id2word)}

        self.model = CommandScorer(input_size=self.MAX_VOCAB_SIZE, hidden_size=128)
        self.optimizer = optim.Adam(self.model.parameters(), 0.00003)

        self.mode = "test"

    def train(self):
        self.mode = "train"
        self.stats = {"max": defaultdict(list), "mean": defaultdict(list)}
        self.transitions = []
        self.model.reset_hidden(1)
        self.last_score = 0
        self.no_train_step = 0

    def test(self):
        self.mode = "test"
        self.model.reset_hidden(1)

    @property
    def infos_to_request(self) -> EnvInfos:
        return EnvInfos(description=True, inventory=True, admissible_commands=True,
                        has_won=True, has_lost=True)

    def _get_word_id(self, word):
        if word not in self.word2id:
            if len(self.word2id) >= self.MAX_VOCAB_SIZE:
                return self.word2id["<UNK>"]

            self.id2word.append(word)
            self.word2id[word] = len(self.word2id)

        return self.word2id[word]

    def _tokenize(self, text):
        # Simple tokenizer: strip out all non-alphabetic characters.
        text = re.sub("[^a-zA-Z0-9\- ]", " ", text)
        word_ids = list(map(self._get_word_id, text.split()))
        return word_ids

    def _process(self, texts):
        texts = list(map(self._tokenize, texts))
        max_len = max(len(l) for l in texts)
        padded = np.ones((len(texts), max_len)) * self.word2id["<PAD>"]

        for i, text in enumerate(texts):
            padded[i, :len(text)] = text

        padded_tensor = torch.from_numpy(padded).type(torch.long).to(device)
        padded_tensor = padded_tensor.permute(1, 0)  # Batch x Seq => Seq x Batch
        return padded_tensor

    def _discount_rewards(self, last_values):
        returns, advantages = [], []
        R = last_values.data
        for t in reversed(range(len(self.transitions))):
            rewards, _, _, values = self.transitions[t]
            R = rewards + self.GAMMA * R
            adv = R - values
            returns.append(R)
            advantages.append(adv)

        return returns[::-1], advantages[::-1]

    def act(self, obs: str, score: int, done: bool, infos: Mapping[str, Any]) -> Optional[str]:

        # Build agent's observation: feedback + look + inventory.
        input_ = "{}\n{}\n{}".format(obs, infos["description"], infos["inventory"])

        # Tokenize and pad the input and the commands to chose from.
        input_tensor = self._process([input_])
        commands_tensor = self._process(infos["admissible_commands"])

        # Get our next action and value prediction.
        outputs, indexes, values = self.model(input_tensor, commands_tensor)
        action = infos["admissible_commands"][indexes[0]]

        if self.mode == "test":
            if done:
                self.model.reset_hidden(1)
            return action

        self.no_train_step += 1

        if self.transitions:
            reward = score - self.last_score  # Reward is the gain/loss in score.
            self.last_score = score
            if infos["has_won"]:
                reward += 100
            if infos["has_lost"]:
                reward -= 100

            self.transitions[-1][0] = reward  # Update reward information.

        self.stats["max"]["score"].append(score)
        if self.no_train_step % self.UPDATE_FREQUENCY == 0:
            # Update model
            returns, advantages = self._discount_rewards(values)

            loss = 0
            for transition, ret, advantage in zip(self.transitions, returns, advantages):
                reward, indexes_, outputs_, values_ = transition

                advantage = advantage.detach()  # Block gradients flow here.
                probs = F.softmax(outputs_, dim=2)
                log_probs = torch.log(probs)
                log_action_probs = log_probs.gather(2, indexes_)
                policy_loss = (-log_action_probs * advantage).sum()
                value_loss = (.5 * (values_ - ret) ** 2.).sum()
                entropy = (-probs * log_probs).sum()
                loss += policy_loss + 0.5 * value_loss - 0.1 * entropy

                self.stats["mean"]["reward"].append(reward)
                self.stats["mean"]["policy"].append(policy_loss.item())
                self.stats["mean"]["value"].append(value_loss.item())
                self.stats["mean"]["entropy"].append(entropy.item())
                self.stats["mean"]["confidence"].append(torch.exp(log_action_probs).item())

            if self.no_train_step % self.LOG_FREQUENCY == 0:
                msg = "{}. ".format(self.no_train_step)
                msg += "  ".join("{}: {:.3f}".format(k, np.mean(v)) for k, v in self.stats["mean"].items())
                msg += "  " + "  ".join("{}: {}".format(k, np.max(v)) for k, v in self.stats["max"].items())
                msg += "  vocab: {}".format(len(self.id2word))
                print(msg)
                self.stats = {"max": defaultdict(list), "mean": defaultdict(list)}

            loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(), 40)
            self.optimizer.step()
            self.optimizer.zero_grad()

            self.transitions = []
            self.model.reset_hidden(1)
        else:
            # Keep information about transitions for Truncated Backpropagation Through Time.
            self.transitions.append([None, indexes, outputs, values])  # Reward will be set on the next call

        if done:
            self.last_score = 0  # Will be starting a new episode. Reset the last score.

        return action