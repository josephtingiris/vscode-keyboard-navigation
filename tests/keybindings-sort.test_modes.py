#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

[WIP] Tests sorting modes in `bin/keybindings-sort.py`.
"""
import unittest
import subprocess
import json
import re
import sys
from textwrap import dedent

import os

# Resolve script path relative to repository root (tests may run with CWD=tests/)
SCRIPT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'bin', 'keybindings-sort.py'))

def run_sort(input_json, args=None):
    cmd = [sys.executable, SCRIPT]
    if args:
        cmd += args
    proc = subprocess.run(cmd, input=input_json.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc

class ModeTests(unittest.TestCase):
    def test_positive_prefers_positive(self):
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
        proc = run_sort(data, ['--primary', 'when', '--group-sorting', 'positive'])
        out = proc.stdout.decode('utf-8')
        # extract when values in output order
        whens = re.findall(r'"when"\s*:\s*"([^"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        self.assertEqual(whens[0].strip(), 'foo')
        self.assertEqual(whens[1].strip(), '!foo')

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
        proc = run_sort(data, ['--primary', 'when', '--group-sorting', 'negative'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        self.assertEqual(whens[0].strip(), '!foo')
        self.assertEqual(whens[1].strip(), 'foo')

    def test_natural_sorts_numerically(self):
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
        proc = run_sort(data, ['--primary', 'when', '--group-sorting', 'natural'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        # natural sort: view2 before view10
        self.assertEqual(whens[0].strip(), 'view2')
        self.assertEqual(whens[1].strip(), 'view10')

    def test_beta_aliases_positive(self):
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
        proc = run_sort(data, ['--primary', 'when', '--group-sorting', 'beta'])
        out = proc.stdout.decode('utf-8')
        whens = re.findall(r'"when"\s*:\s*"([^"]*)"', out)
        self.assertGreaterEqual(len(whens), 2)
        self.assertEqual(whens[0].strip(), 'foo')
        self.assertEqual(whens[1].strip(), '!foo')

if __name__ == '__main__':
    unittest.main()
