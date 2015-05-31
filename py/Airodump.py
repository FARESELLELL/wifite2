#!/usr/bin/python

from Process import Process
from Configuration import Configuration
from Target import Target
from Client import Client
from Wash import Wash

import os

class Airodump(object):
    ''' Wrapper around airodump-ng program '''

    def __init__(self, interface=None,       channel=None,         encryption=None, \
                             wps=False, target_bssid=None, output_file_prefix='airodump', \
                        ivs_only=False):
        ''' Constructor, sets things up '''

        Configuration.initialize()

        if interface == None:
            interface = Configuration.interface
        if interface == None:
            raise Exception("Wireless interface must be defined (-i)")
        self.interface = interface

        self.targets = []

        if channel == None:
            channel = Configuration.target_channel
        self.channel = channel

        self.encryption = encryption
        self.wps = wps

        self.target_bssid = target_bssid
        self.output_file_prefix = output_file_prefix
        self.ivs_only = ivs_only


    def __enter__(self):
        '''
            Setting things up for this context.
            Called at start of 'with Airodump(...) as x:'
        '''
        self.delete_airodump_temp_files()

        self.csv_file_prefix = Configuration.temp() + self.output_file_prefix

        # Build the command
        command = [
            'airodump-ng',
            self.interface,
            '-a', # Only show associated clients
            '-w', self.csv_file_prefix # Output file prefix
        ]
        if self.channel:
            command.extend(['-c', str(self.channel)])
        if self.encryption:
            command.extend(['--enc', self.encryption])
        if self.wps:
            command.extend(['--wps'])
        if self.target_bssid:
            command.extend(['--bssid', self.target_bssid])

        if self.ivs_only:
            command.extend(['--output-format', 'ivs,csv'])
        else:
            command.extend(['--output-format', 'pcap,csv'])

        # Start the process
        self.pid = Process(command, devnull=True)
        return self


    def __exit__(self, type, value, traceback):
        '''
            Tearing things down since the context is being exited.
            Called after 'with Airodump(...)' goes out of scope.
        '''
        # Kill the process
        self.pid.interrupt()

        # Delete temp files
        self.delete_airodump_temp_files()


    def find_files(self, endswith=None):
        ''' Finds all files in the temp directory that start with the output_file_prefix '''
        result = []
        for fil in os.listdir(Configuration.temp()):
            if fil.startswith(self.output_file_prefix):
                if not endswith or fil.endswith(endswith):
                    result.append(Configuration.temp() + fil)
        return result

    def delete_airodump_temp_files(self):
        ''' Deletes airodump* files in the temp directory '''
        for fil in self.find_files():
            os.remove(fil)

    def get_targets(self):
        ''' Parses airodump's CSV file, returns list of Targets '''
        # Find the .CSV file
        csv_filename = None
        for fil in self.find_files(endswith='-01.csv'):
            # Found the file
            csv_filename = fil
            break
        if csv_filename == None or not os.path.exists(csv_filename):
            # No file found
            return self.targets

        # Parse the .CSV file
        targets = Airodump.get_targets_from_csv(csv_filename)
        targets = Airodump.filter_targets(targets, wep=True, wpa=True, opn=False)

        # Check targets for WPS
        capfile = csv_filename[:-3] + 'cap'
        Wash.check_for_wps_and_update_targets(capfile, targets)

        # Sort by power
        targets.sort(key=lambda x: x.power, reverse=True)

        self.targets = targets

        return self.targets


    @staticmethod
    def get_targets_from_csv(csv_filename):
        '''
            Returns list of Target objects parsed from CSV file
        '''
        targets = []
        import csv
        with open(csv_filename, 'rb') as csvopen:
            csv_reader = csv.reader(csvopen, delimiter=',')
            hit_clients = False
            for row in csv_reader:
                # Each "row" is a list of fields for a target/client

                if len(row) == 0: continue

                if row[0].strip() == 'BSSID':
                    # This is the "header" for the list of Targets
                    hit_clients = False
                    continue

                elif row[0].strip() == 'Station MAC':
                    # This is the "header" for the list of Clients
                    hit_clients = True
                    continue

                if hit_clients:
                    # The current row corresponds to a "Client" (computer)
                    client = Client(row)

                    if 'not associated' in client.bssid:
                        # Ignore unassociated clients
                        continue

                    # Add this client to the appropriate Target
                    for t in targets:
                        if t.bssid == client.bssid:
                            t.clients.append(client)
                            break

                else:
                    # The current row corresponds to a "Target" (router)
                    target = Target(row)

                    if target.essid_len == 0:
                        # Ignore empty/blank ESSIDs
                        continue

                    targets.append(target)
        return targets

    @staticmethod
    def filter_targets(targets, wep=True, wpa=True, opn=False):
        ''' Filters targets based on encryption '''
        result = []
        for target in targets:
            if wep and 'WEP' in target.encryption:
                result.append(target)
            elif wpa and 'WPA' in target.encryption:
                result.append(target)
            elif opn and 'OPN' in target.encryption:
                result.append(target)
        return result


if __name__ == '__main__':
    ''' Example usage. wlan0mon should be in Monitor Mode '''
    with Airodump() as airodump:

        from time import sleep
        sleep(7)

        from Color import Color

        targets = airodump.get_targets()
        Target.print_header()
        for (index, target) in enumerate(targets):
            index += 1
            Color.pl('   {G}%s %s' % (str(index).rjust(3), target))

    Configuration.delete_temp()
