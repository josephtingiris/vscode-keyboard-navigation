#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Tests keynav sorting modes.
"""

import os
import re
import subprocess
import sys

from textwrap import dedent

import unittest


#
# globals & constants
#


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_INPUT_FULL = os.path.join(REPO_ROOT, "references", "keybindings.surface.all.jsonc")
DEFAULT_INPUT_QUICK_SMALL = os.path.join(REPO_ROOT, "references", "keybindings.surface.vi.jsonc")

KEYBINDINGS_SORT_PY = os.path.join(REPO_ROOT, "bin", "keybindings-sort.py")


#
# classes
#


class ModeTests(unittest.TestCase):
    def test_positive_prefers_positive(self):
        # ``positive`` group-sorting has no impact when the primary key is
        # ``when``; a final literal sort on the clause preserves the input
        # sequence.
        data = dedent('''
        [
          {
            "key": "a",
            "when": "!foo"
          },
          {
            "key": "b",
            "when": "foo"
          }
        ]
        ''')
        proc = _run_sort(data, ['--primary', 'when', '--group-sorting', 'positive'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^\"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        # original order retained
        self.assertEqual(whens[0].strip(), '!foo')
        self.assertEqual(whens[1].strip(), 'foo')

    def test_negative_prefers_negative(self):
        data = dedent('''
        [
          {
            "key": "a",
            "when": "!foo"
          },
          {
            "key": "b",
            "when": "foo"
          }
        ]
        ''')
        proc = _run_sort(data, ['--primary', 'when', '--group-sorting', 'negative'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^\"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        self.assertEqual(whens[0].strip(), '!foo')
        self.assertEqual(whens[1].strip(), 'foo')

    def test_natural_sorts_numerically(self):
        # natural mode is ignored when ``--primary when``; order matches input.
        data = dedent('''
        [
          {
            "key": "a",
            "when": "view10"
          },
          {
            "key": "b",
            "when": "view2"
          }
        ]
        ''')
        proc = _run_sort(data, ['--primary', 'when', '--group-sorting', 'natural'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^\"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        self.assertEqual(whens[0].strip(), 'view10')
        self.assertEqual(whens[1].strip(), 'view2')

    def test_positive_aliases_positive(self):
      # ``positive`` group-sorting (formerly aliased by ``beta``) prefers
      # positive ordering when sorting tokens inside a ``when`` clause.
        data = dedent('''
        [
          {
            "key": "a",
            "when": "!foo"
          },
          {
            "key": "b",
            "when": "foo"
          }
        ]
        ''')
        proc = _run_sort(data, ['--primary', 'when', '--group-sorting', 'positive'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^\"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        self.assertEqual(whens[0].strip(), '!foo')
        self.assertEqual(whens[1].strip(), 'foo')


#
# functions
#


def _run_sort(input_json, args=None):
    cmd = [sys.executable, KEYBINDINGS_SORT_PY]
    if args:
        cmd += args
    proc = subprocess.run(cmd, input=input_json.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


#
# main
#


if __name__ == '__main__':
    unittest.main()
