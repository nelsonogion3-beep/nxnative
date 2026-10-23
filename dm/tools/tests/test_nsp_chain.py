"""NSP script chain files (scripts/build_ipa_from_nsp.py chain_header, chain_tables): a registered profile's stale chain version header is written again and a current one left alone,
only the c1 / uniform extent tables that are missing (they are not committed) or name another chain are made (GitHub issue #78), and no step's reuse key counts them;
no game files, keys or Xcode needed (temporary files only in a temporary folder)."""
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / 'scripts/build_ipa_from_nsp.py'
spec = importlib.util.spec_from_file_location('build_ipa_from_nsp', SCRIPT)
nsp = importlib.util.module_from_spec(spec); spec.loader.exec_module(nsp)
GAME = '010014E00DB56000'   # a small profile (Digimon Story Cyber Sleuth): dmsh_chain.py hashes its tables


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.said = []
        for cm in (mock.patch.object(nsp, 'PROG', mock.Mock()), mock.patch.object(nsp, 'say', self.said.append)):
            cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)


class Header(Base):
    def setUp(self):
        super().setUp()
        self.dir = self.tmp / 'profiles' / GAME
        shutil.copytree(REPO / 'dm/games' / GAME, self.dir)
        self.env = dict(os.environ, DM_GAME=GAME, DM_GAMES_DIR=str(self.dir.parent), DM_GAMES_FIRST='1')
        self.g = types.SimpleNamespace(table=lambda n: self.dir / n)

    def header(self):
        nsp.chain_header(sys.executable, REPO, self.env, self.tmp / 'logs', self.g)

    def test_stale_rewritten(self):
        want = nsp.chain_of(self.g)
        (self.dir / 'dmsh_chain.h').write_text('#define DMSH_CHAIN "000000000000"\n')
        self.header()
        self.assertEqual(nsp.chain_of(self.g), want)
        self.assertEqual(len(self.said), 1); self.assertIn('held 000000000000', self.said[0])

    def test_missing_written(self):
        want = nsp.chain_of(self.g)
        (self.dir / 'dmsh_chain.h').unlink()
        self.header()
        self.assertEqual(nsp.chain_of(self.g), want)
        self.assertIn('held no version', self.said[0])

    def test_current_untouched(self):
        p = self.dir / 'dmsh_chain.h'; os.utime(p, (1, 1))
        self.header()
        self.assertEqual(p.stat().st_mtime, 1); self.assertEqual(self.said, [])


class Tables(Base):
    CHAIN = '0123456789ab'

    def setUp(self):
        super().setUp()
        self.sh = self.tmp / 'shader'; (self.sh / 'cache' / f'b-{self.CHAIN}').mkdir(parents=True)
        self.g = types.SimpleNamespace(table=lambda n: self.tmp / n)
        self.ran = []
        cm = mock.patch.object(nsp, 'run', lambda cmd, log, env=None: self.ran.append(Path(cmd[1]).name)); cm.__enter__(); self.addCleanup(cm.__exit__, None, None, None)

    def tables(self, c1, cb, every=False):
        for n, chain in (('c1_full.tsv', c1), ('cb_extent.tsv', cb)):
            if chain: (self.tmp / n).write_text(f'# chain b-{chain} 2026-10-23T00:00:00+00:00\n')
        return nsp.chain_tables(sys.executable, REPO, self.sh, {}, self.tmp / 'logs', self.g, self.CHAIN, every)

    def test_current_kept(self):
        self.assertTrue(self.tables(self.CHAIN, self.CHAIN))
        self.assertEqual(self.ran, []); self.assertEqual(self.said, [])

    def test_stale_made_again(self):
        self.assertTrue(self.tables(self.CHAIN, 'fc6c0368c7b9'))
        self.assertEqual(self.ran, ['cb_extent.py']); self.assertIn('named b-fc6c0368c7b9', self.said[0])

    def test_missing_made(self):   # a checkout's first pack: the tables are not in the repository
        self.assertTrue(self.tables(None, None))
        self.assertEqual(self.ran, ['c1_guard.py', 'cb_extent.py']); self.assertIn('c1_full.tsv missing', self.said[0])

    def test_every(self):   # a provisional or derived profile: both, current or not
        self.assertTrue(self.tables(self.CHAIN, self.CHAIN, every=True))
        self.assertEqual(self.ran, ['c1_guard.py', 'cb_extent.py']); self.assertEqual(self.said, [])

    def test_no_mac_outputs(self):   # build_shaders then builds again (reuse) or stops (after a build)
        shutil.rmtree(self.sh / 'cache')
        self.assertFalse(self.tables('fc6c0368c7b9', self.CHAIN))
        self.assertEqual(self.ran, [])
        self.assertTrue(self.tables(self.CHAIN, self.CHAIN))   # nothing to make: no Mac outputs needed

    def test_not_profile_inputs(self):   # the steps' reuse keys leave out what the iOS shader step makes
        for n in ('game.tsv', 'shader_map.tsv', 'c1_full.tsv', 'cb_extent.tsv'): (self.tmp / n).write_text('')
        self.assertEqual([p.name for p in nsp.profile_files(types.SimpleNamespace(dir=self.tmp))], ['game.tsv', 'shader_map.tsv'])


if __name__ == '__main__':
    unittest.main()
