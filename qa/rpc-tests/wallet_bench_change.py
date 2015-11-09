#!/usr/bin/env python2
# Copyright (c) 2015 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# Benchmark wallet with different settings of MIN_CHANGE
#

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import *

#Set colors 
cOn = cOff = "" 
if (os.name == 'posix'): 
    h = '\033[1m' 
    H = '\033[0m'

def read_decimals(filename):
    with open(filename) as f:
        return map(Decimal, f)

def min_bal(values):
    bal = 0
    min_bal = 0
    for val in values:
        bal += val
        min_bal = min(bal, min_bal)
    return min_bal

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    # http://stackoverflow.com/a/312464
    for i in xrange(0, len(l), n):
        yield l[i:i+n]

class WalletBenchChange(BitcoinTestFramework):

    def wipe_balance(self, node):
        unspent = node.listunspent(0)
        if len(unspent) == 0:
            return
        inputs = [{"txid":i["txid"], "vout":i["vout"]} for i in unspent]
        outputs = {self.miner.getnewaddress():0}
        raw = node.createrawtransaction(inputs, outputs)
        signed = node.signrawtransaction(raw)
        node.sendrawtransaction(signed["hex"], True)

    def setup_chain(self):
        self.num_users = 2#7 # -minchange range is derived from this
        print("Initializing test directory "+self.options.tmpdir)
        # Also init miner chain
        initialize_chain_clean(self.options.tmpdir, 1 + self.num_users)

    def setup_network(self):
        self.users_min_change = [""] * self.num_users
        self.nodes = []
        self.users = []
        relay_fee = '-minrelaytxfee=0.00000001' # lower isDust()

        self.nodes.append(start_node(0, self.options.tmpdir, [relay_fee]))
        self.miner = self.nodes[0]
        for i in range(self.num_users):
            self.users_min_change[i] = str(10 * pow(Decimal(10), -i + 8))
            print("Create node with\nMIN_CHANGE=" + self.users_min_change[i])
            self.nodes.append(start_node(i + 1, self.options.tmpdir, [
                                    '-minchange=' + self.users_min_change[i],
                                    relay_fee]))
            self.users.append(self.nodes[i + 1])
            connect_nodes_bi(self.nodes, 0, i + 1) # star topology
        self.is_network_split = False
        self.sync_all()

    def generate_and_sync(self, num):
        self.sync_all()
        self.miner.generate(num)
        self.sync_all()

    def run_test(self):
        receive_t = [r for r in read_decimals(__file__ + '.receive') if r != Decimal(".00000001")]
        send_t = read_decimals(__file__ + '.send')
        all_t = [a for a in read_decimals(__file__ + '.all') if a != Decimal(".00000001")]
        all_t.insert(0, -min_bal(all_t)) # make sure balance >= 0
        all_t.insert(0, len(send_t) * Decimal(".00000001")) # make sure to include the fees

        assert(len(receive_t) == 24388 - 371) # 371 single satoshi inputs dropped
        assert(len(send_t) == 11860)
        assert(len(all_t) == 11860 + 24388 - 371 + 2)

        ######## Only run test for so long
        short_test_dur = -1
        short_test_dur = 50
        if short_test_dur != -1:
            receive_t = receive_t[0:short_test_dur]
            send_t = send_t[0:short_test_dur]
            all_t = all_t[0:short_test_dur]

        # Generate inital coins to send out
        self.generate_and_sync(151)

        tests = {"big_chunks" : None, "ping-pong" : None}

        for test in tests:
            txo_diff_num = [None] * self.num_users
            for i in range(self.num_users):
                print "Run test %s%s for MIN_CHANGE=%s%s" % (h, test, str(self.users_min_change[i]), H)
                if test is "big_chunks":
                    txo_diff_num[i] = self.run_transactions_chunks(receive_t, send_t, self.users[i])
                if test is "ping-pong":
                    txo_diff_num[i] = self.run_transactions_ping_pong(all_t, self.users[i])

                print "============\n %stxo_diff_num = %s%s\n" % (h, str(txo_diff_num[i]), H)

                # Cleanup
                self.wipe_balance(self.users[i])
                self.generate_and_sync(10)
                assert_equal(self.users[i].getmempoolinfo()["size"], 0)
                assert_equal(self.users[i].getbalance(), 0)

                tests[test] = txo_diff_num

        print "%sTest results:%s" % (h, H)
        print "MIN_CHANGE = ", self.users_min_change
        print tests

    def run_transactions_chunks(self, receive_t, send_t, user):
        # Send out funds to the user
        for chunk in chunks(receive_t, 2750):
             self.miner.sendmany("", {user.getnewaddress():r for r in chunk})
        self.generate_and_sync(10)
        assert_equal(self.miner.getmempoolinfo()["size"], 0)

        # Assert everything was included in the blocks
        assert_equal(len(user.listunspent()), len(receive_t))
        assert_equal(user.getbalance(), sum(receive_t))

        # Remember utxoutset
        txo_0 = user.gettxoutsetinfo()["txouts"]

        # generate blocks and send transactions in the meantime
        blocks = 0
        print "%s txouts (initial)" % str(txo_0)
        for chunk in chunks(send_t, 25):
            for s in chunk:
                user.sendtoaddress(self.miner.getnewaddress(), -s)
            blocks += 1
            self.generate_and_sync(1)
            print "%s txo_error" % str(txo_0 + blocks)
        assert_equal(user.getmempoolinfo()["size"], 0)
        print "%s total txout size" % user.gettxoutsetinfo()["txouts"]
        return user.gettxoutsetinfo()["txouts"] - blocks - txo_0

    def run_transactions_ping_pong(self, all_t, user):
        user_a = user.getnewaddress() # Reuse private key

        assert_equal(user.getmempoolinfo()["size"], 0)
        txo_error = user.gettxoutsetinfo()["txouts"]
        print "%s txo_error (initial)" % txo_error 
        for a in all_t:
            if a < 0:
                user.sendtoaddress(self.miner.getnewaddress(), -a)
            else:
                self.generate_and_sync(1)
                assert_equal(user.getmempoolinfo()["size"], 0)
                txo_tmp = user.gettxoutsetinfo()["txouts"]
                self.miner.sendtoaddress(user_a, a)
                self.generate_and_sync(1)
                # Don't count blocks and miner transaction effects
                txo_error += 2 + user.gettxoutsetinfo()["txouts"] - txo_tmp
                print "%s txo_error" % txo_error
        self.generate_and_sync(1)
        assert_equal(user.getmempoolinfo()["size"], 0)
        txo_error += 1
        print "%s total txout size" % user.gettxoutsetinfo()["txouts"]
        return user.gettxoutsetinfo()["txouts"] - txo_error

if __name__ == '__main__':
    WalletBenchChange().main()
