# Copyright (C) 2010  Internet Systems Consortium.
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND INTERNET SYSTEMS CONSORTIUM
# DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
# INTERNET SYSTEMS CONSORTIUM BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING
# FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION
# WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import unittest
import sys
import os
import tempfile
import time
import socket
from isc.datasrc import sqlite3_ds
from isc.notify import notify_out, SOCK_DATA

# our fake socket, where we can read and insert messages
class MockSocket():
    def __init__(self):
        self._local_sock, self._remote_sock = socket.socketpair()

    def connect(self, to):
        pass

    def fileno(self):
        return self._local_sock.fileno()

    def close(self):
        self._local_sock.close()
        self._remote_sock.close()

    def sendto(self, data, flag, dst):
        return self._local_sock.send(data)

    def recvfrom(self, length):
        data = self._local_sock.recv(length)
        return (data, None)

    # provide a remote end which can write data to MockSocket for testing.
    def remote_end(self):
        return self._remote_sock

# We subclass the ZoneNotifyInfo class we're testing here, only
# to override the prepare_notify_out() method.
class MockZoneNotifyInfo(notify_out.ZoneNotifyInfo):
    def prepare_notify_out(self):
        super().prepare_notify_out();
        self._sock.close()
        self._sock = MockSocket()

class TestZoneNotifyInfo(unittest.TestCase):
    def setUp(self):
        self.info = notify_out.ZoneNotifyInfo('example.net.', 'IN')

    def test_prepare_finish_notify_out(self):
        self.info.prepare_notify_out()
        self.assertNotEqual(self.info._sock, None)
        self.assertIsNone(self.info._notify_current)

        self.info.finish_notify_out()
        self.assertEqual(self.info._sock, None)

    def test_set_next_notify_target(self):
        self.info.notify_slaves.append(('127.0.0.1', 53))
        self.info.notify_slaves.append(('1.1.1.1', 5353))
        self.info.prepare_notify_out()
        self.assertEqual(self.info.get_current_notify_target(), ('127.0.0.1', 53))

        self.assertEqual('127.0.0.1#53', notify_out.addr_to_str(('127.0.0.1', 53)))
        self.info.set_next_notify_target()
        self.assertEqual(self.info.get_current_notify_target(), ('1.1.1.1', 5353))
        self.info.set_next_notify_target()
        self.assertIsNone(self.info.get_current_notify_target())

        temp_info = notify_out.ZoneNotifyInfo('example.com.', 'IN')
        temp_info.prepare_notify_out()
        self.assertIsNone(temp_info.get_current_notify_target())


class TestNotifyOut(unittest.TestCase):
    def setUp(self):
        self._db_file = tempfile.NamedTemporaryFile(delete=False)
        sqlite3_ds.load(self._db_file.name, 'example.net.', self._example_net_data_reader)
        sqlite3_ds.load(self._db_file.name, 'example.com.', self._example_com_data_reader)
        self._notify = notify_out.NotifyOut(self._db_file.name)
        self._notify._notify_infos[('example.com.', 'IN')] = MockZoneNotifyInfo('example.com.', 'IN')
        self._notify._notify_infos[('example.com.', 'CH')] = MockZoneNotifyInfo('example.com.', 'CH')
        self._notify._notify_infos[('example.net.', 'IN')] = MockZoneNotifyInfo('example.net.', 'IN')
        self._notify._notify_infos[('example.org.', 'IN')] = MockZoneNotifyInfo('example.org.', 'IN')
        self._notify._notify_infos[('example.org.', 'CH')] = MockZoneNotifyInfo('example.org.', 'CH')

        net_info = self._notify._notify_infos[('example.net.', 'IN')]
        net_info.notify_slaves.append(('127.0.0.1', 53))
        net_info.notify_slaves.append(('1.1.1.1', 5353))
        com_info = self._notify._notify_infos[('example.com.', 'IN')]
        com_info.notify_slaves.append(('1.1.1.1', 5353))
        com_ch_info = self._notify._notify_infos[('example.com.', 'CH')]
        com_ch_info.notify_slaves.append(('1.1.1.1', 5353))

    def tearDown(self):
        self._db_file.close()
        os.unlink(self._db_file.name)

    def test_send_notify(self):
        notify_out._MAX_NOTIFY_NUM = 2

        self._notify.send_notify('example.net')
        self.assertEqual(self._notify.notify_num, 1)
        self.assertEqual(self._notify._notifying_zones[0], ('example.net.', 'IN'))

        self._notify.send_notify('example.com')
        self.assertEqual(self._notify.notify_num, 2)
        self.assertEqual(self._notify._notifying_zones[1], ('example.com.', 'IN'))

        # notify_num is equal to MAX_NOTIFY_NUM, append it to waiting_zones list.
        self._notify.send_notify('example.com', 'CH')
        self.assertEqual(self._notify.notify_num, 2)
        self.assertEqual(1, len(self._notify._waiting_zones))

        # zone_id is already in notifying_zones list, append it to waiting_zones list.
        self._notify.send_notify('example.net')
        self.assertEqual(2, len(self._notify._waiting_zones))
        self.assertEqual(self._notify._waiting_zones[1], ('example.net.', 'IN'))

        # zone_id is already in waiting_zones list, skip it.
        self._notify.send_notify('example.net')
        self.assertEqual(2, len(self._notify._waiting_zones))

        # has no slave masters, skip it.
        self._notify.send_notify('example.org.', 'CH')
        self.assertEqual(self._notify.notify_num, 2)
        self.assertEqual(2, len(self._notify._waiting_zones))

        self._notify.send_notify('example.org.')
        self.assertEqual(self._notify.notify_num, 2)
        self.assertEqual(2, len(self._notify._waiting_zones))

    def test_wait_for_notify_reply(self):
        self._notify.send_notify('example.net.')
        self._notify.send_notify('example.com.')

        notify_out._MAX_NOTIFY_NUM = 2
        self._notify.send_notify('example.org.')
        replied_zones, timeout_zones = self._notify._wait_for_notify_reply()
        self.assertEqual(len(replied_zones), 0)
        self.assertEqual(len(timeout_zones), 2)

        # Now make one socket be readable
        self._notify._notify_infos[('example.net.', 'IN')].notify_timeout = time.time() + 10
        self._notify._notify_infos[('example.com.', 'IN')].notify_timeout = time.time() + 10

        #Send some data to socket 12340, to make the target socket be readable
        self._notify._notify_infos[('example.net.', 'IN')]._sock.remote_end().send(b'data')
        replied_zones, timeout_zones = self._notify._wait_for_notify_reply()
        self.assertEqual(len(replied_zones), 1)
        self.assertEqual(len(timeout_zones), 1)
        self.assertTrue(('example.net.', 'IN') in replied_zones.keys())
        self.assertTrue(('example.com.', 'IN') in timeout_zones.keys())
        self.assertLess(time.time(), self._notify._notify_infos[('example.com.', 'IN')].notify_timeout)

    def test_wait_for_notify_reply_2(self):
        # Test the returned value when the read_side socket is readable.
        self._notify.send_notify('example.net.')
        self._notify.send_notify('example.com.')

        # Now make one socket be readable
        self._notify._notify_infos[('example.net.', 'IN')].notify_timeout = time.time() + 10
        self._notify._notify_infos[('example.com.', 'IN')].notify_timeout = time.time() + 10
        self._notify._read_sock, self._notify._write_sock = socket.socketpair()
        self._notify._write_sock.send(SOCK_DATA)
        replied_zones, timeout_zones = self._notify._wait_for_notify_reply()
        self.assertEqual(0, len(replied_zones))
        self.assertEqual(0, len(timeout_zones))

    def test_notify_next_target(self):
        self._notify.send_notify('example.net.')
        self._notify.send_notify('example.com.')
        notify_out._MAX_NOTIFY_NUM = 2
        # zone example.org. has no slave servers.
        self._notify.send_notify('example.org.')
        self._notify.send_notify('example.com.', 'CH')

        info = self._notify._notify_infos[('example.net.', 'IN')]
        self._notify._notify_next_target(info)
        self.assertEqual(0, info.notify_try_num)
        self.assertEqual(info.get_current_notify_target(), ('1.1.1.1', 5353))
        self.assertEqual(2, self._notify.notify_num)
        self.assertEqual(1, len(self._notify._waiting_zones))

        self._notify._notify_next_target(info)
        self.assertEqual(0, info.notify_try_num)
        self.assertIsNone(info.get_current_notify_target())
        self.assertEqual(2, self._notify.notify_num)
        self.assertEqual(0, len(self._notify._waiting_zones))

        example_com_info = self._notify._notify_infos[('example.com.', 'IN')]
        self._notify._notify_next_target(example_com_info)
        self.assertEqual(1, self._notify.notify_num)
        self.assertEqual(1, len(self._notify._notifying_zones))
        self.assertEqual(0, len(self._notify._waiting_zones))

    def test_handle_notify_reply(self):
        self.assertEqual(notify_out._BAD_REPLY_PACKET, self._notify._handle_notify_reply(None, b'badmsg'))
        example_com_info = self._notify._notify_infos[('example.com.', 'IN')]
        example_com_info.notify_msg_id = 0X2f18

        # test with right notify reply message
        data = b'\x2f\x18\xa0\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\03com\x00\x00\x06\x00\x01'
        self.assertEqual(notify_out._REPLY_OK, self._notify._handle_notify_reply(example_com_info, data))

        # test with unright query id
        data = b'\x2e\x18\xa0\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\03com\x00\x00\x06\x00\x01'
        self.assertEqual(notify_out._BAD_QUERY_ID, self._notify._handle_notify_reply(example_com_info, data))

        # test with unright query name
        data = b'\x2f\x18\xa0\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\03net\x00\x00\x06\x00\x01'
        self.assertEqual(notify_out._BAD_QUERY_NAME, self._notify._handle_notify_reply(example_com_info, data))

        # test with unright opcode
        data = b'\x2f\x18\x80\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\03com\x00\x00\x06\x00\x01'
        self.assertEqual(notify_out._BAD_OPCODE, self._notify._handle_notify_reply(example_com_info, data))

        # test with unright qr
        data = b'\x2f\x18\x10\x10\x00\x01\x00\x00\x00\x00\x00\x00\x07example\03com\x00\x00\x06\x00\x01'
        self.assertEqual(notify_out._BAD_QR, self._notify._handle_notify_reply(example_com_info, data))

    def test_send_notify_message_udp(self):
        example_com_info = self._notify._notify_infos[('example.net.', 'IN')]
        example_com_info.prepare_notify_out()
        ret = self._notify._send_notify_message_udp(example_com_info, ('1.1.1.1', 53))
        self.assertTrue(ret)

    def test_zone_notify_handler(self):
        old_send_msg = self._notify._send_notify_message_udp
        def _fake_send_notify_message_udp(va1, va2):
            pass
        self._notify._send_notify_message_udp = _fake_send_notify_message_udp
        self._notify.send_notify('example.net.')
        self._notify.send_notify('example.com.')
        notify_out._MAX_NOTIFY_NUM = 2
        self._notify.send_notify('example.org.')

        example_net_info = self._notify._notify_infos[('example.net.', 'IN')]
        example_net_info.prepare_notify_out()

        example_net_info.notify_try_num = 2
        self._notify._zone_notify_handler(example_net_info, notify_out._EVENT_TIMEOUT)
        self.assertEqual(3, example_net_info.notify_try_num)

        time1 = example_net_info.notify_timeout
        self._notify._zone_notify_handler(example_net_info, notify_out._EVENT_TIMEOUT)
        self.assertEqual(4, example_net_info.notify_try_num)
        self.assertGreater(example_net_info.notify_timeout, time1 + 2) # bigger than 2 seconds

        cur_tgt = example_net_info._notify_current
        example_net_info.notify_try_num = notify_out._MAX_NOTIFY_TRY_NUM
        self._notify._zone_notify_handler(example_net_info, notify_out._EVENT_NONE)
        self.assertNotEqual(cur_tgt, example_net_info._notify_current)

    def _example_net_data_reader(self):
        zone_data = [
        ('example.net.',         '1000',  'IN',  'SOA', 'a.dns.example.net. mail.example.net. 1 1 1 1 1'),
        ('example.net.',         '1000',  'IN',  'NS',  'a.dns.example.net.'),
        ('example.net.',         '1000',  'IN',  'NS',  'b.dns.example.net.'),
        ('example.net.',         '1000',  'IN',  'NS',  'c.dns.example.net.'),
        ('a.dns.example.net.',   '1000',  'IN',  'A',    '1.1.1.1'),
        ('a.dns.example.net.',   '1000',  'IN',  'AAAA', '2:2::2:2'),
        ('b.dns.example.net.',   '1000',  'IN',  'A',    '3.3.3.3'),
        ('b.dns.example.net.',   '1000',  'IN',  'AAAA', '4:4::4:4'),
        ('b.dns.example.net.',   '1000',  'IN',  'AAAA', '5:5::5:5'),
        ('c.dns.example.net.',   '1000',  'IN',  'A',    '6.6.6.6'),
        ('c.dns.example.net.',   '1000',  'IN',  'A',    '7.7.7.7'),
        ('c.dns.example.net.',   '1000',  'IN',  'AAAA', '8:8::8:8')]
        for item in zone_data:
            yield item

    def _example_com_data_reader(self):
        zone_data = [
        ('example.com.',         '1000',  'IN',  'SOA', 'a.dns.example.com. mail.example.com. 1 1 1 1 1'),
        ('example.com.',         '1000',  'IN',  'NS',  'a.dns.example.com.'),
        ('example.com.',         '1000',  'IN',  'NS',  'b.dns.example.com.'),
        ('example.com.',         '1000',  'IN',  'NS',  'c.dns.example.com.'),
        ('a.dns.example.com.',   '1000',  'IN',  'A',    '1.1.1.1'),
        ('b.dns.example.com.',   '1000',  'IN',  'A',    '3.3.3.3'),
        ('b.dns.example.com.',   '1000',  'IN',  'AAAA', '4:4::4:4'),
        ('b.dns.example.com.',   '1000',  'IN',  'AAAA', '5:5::5:5')]
        for item in zone_data:
            yield item

    def test_get_notify_slaves_from_ns(self):
        records = self._notify._get_notify_slaves_from_ns('example.net.')
        self.assertEqual(6, len(records))
        self.assertEqual('8:8::8:8', records[5])
        self.assertEqual('7.7.7.7', records[4])
        self.assertEqual('6.6.6.6', records[3])
        self.assertEqual('5:5::5:5', records[2])
        self.assertEqual('4:4::4:4', records[1])
        self.assertEqual('3.3.3.3', records[0])

        records = self._notify._get_notify_slaves_from_ns('example.com.')
        self.assertEqual(3, len(records))
        self.assertEqual('5:5::5:5', records[2])
        self.assertEqual('4:4::4:4', records[1])
        self.assertEqual('3.3.3.3', records[0])

    def test_init_notify_out(self):
        self._notify._init_notify_out(self._db_file.name)
        self.assertListEqual([('3.3.3.3', 53), ('4:4::4:4', 53), ('5:5::5:5', 53)],
                             self._notify._notify_infos[('example.com.', 'IN')].notify_slaves)

    def test_prepare_select_info(self):
        timeout, valid_fds, notifying_zones = self._notify._prepare_select_info()
        self.assertEqual(notify_out._IDLE_SLEEP_TIME, timeout)
        self.assertListEqual([], valid_fds)

        self._notify._notify_infos[('example.net.', 'IN')]._sock = 1
        self._notify._notify_infos[('example.net.', 'IN')].notify_timeout = time.time() + 5
        timeout, valid_fds, notifying_zones = self._notify._prepare_select_info()
        self.assertGreater(timeout, 0)
        self.assertListEqual([1], valid_fds)

        self._notify._notify_infos[('example.net.', 'IN')]._sock = 1
        self._notify._notify_infos[('example.net.', 'IN')].notify_timeout = time.time() - 5
        timeout, valid_fds, notifying_zones = self._notify._prepare_select_info()
        self.assertEqual(timeout, 0)
        self.assertListEqual([1], valid_fds)

        self._notify._notify_infos[('example.com.', 'IN')]._sock = 2
        self._notify._notify_infos[('example.com.', 'IN')].notify_timeout = time.time() + 5
        timeout, valid_fds, notifying_zones = self._notify._prepare_select_info()
        self.assertEqual(timeout, 0)
        self.assertListEqual([2, 1], valid_fds)

    def test_shutdown(self):
        thread = self._notify.dispatcher()
        self.assertTrue(thread.is_alive())
        self._notify.shutdown()
        self.assertFalse(thread.is_alive())

if __name__== "__main__":
    unittest.main()


