#!/usr/bin/env python3
#
# Copyright (C) 2025 VyOS Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from vyos import ConfigError
from vyos.config import Config
from vyos.configdiff import Diff
from vyos.configdict import node_changed
from vyos.vpp.utils import cli_ifaces_list
from vyos.vpp import VPPControl


def get_config(config=None) -> dict:
    if config:
        conf = config
    else:
        conf = Config()

    base = ['vpp', 'sflow']

    # Get config_dict with default values
    config = conf.get_config_dict(
        base,
        key_mangling=('-', '_'),
        get_first_key=True,
        no_tag_node_value_mangle=True,
        with_defaults=True,
        with_recursive_defaults=True,
    )

    # Get effective config as we need full dictionary for deletion
    effective_config = conf.get_config_dict(
        base,
        key_mangling=('-', '_'),
        effective=True,
        get_first_key=True,
        no_tag_node_value_mangle=True,
    )

    if not config:
        config['remove'] = True
        return config

    config_changed = node_changed(
        conf,
        base,
        key_mangling=('-', '_'),
        recursive=True,
        expand_nodes=Diff.DELETE | Diff.ADD,
    )

    # Add list of VPP interfaces to the config
    config.update({'vpp_ifaces': cli_ifaces_list(conf)})

    if effective_config:
        config.update({'effective': effective_config})

    return config


def verify(config):
    if 'remove' in config:
        return None

    # Check if interface section exists
    if 'interface' not in config:
        return None

    # Verify that all interfaces specified exist in VPP
    for interface in config['interface'].get('interface', []):
        if interface not in config['vpp_ifaces']:
            raise ConfigError(f'{interface} must be a VPP interface for sFlow monitoring')

    # Verify sample rate is a positive integer
    if 'sample_rate' in config:
        try:
            sample_rate = int(config['sample_rate'])
            if sample_rate <= 0:
                raise ConfigError('sFlow sample rate must be a positive integer')
        except ValueError:
            raise ConfigError('sFlow sample rate must be a valid integer')


def generate(config):
    # No templates to render for sFlow
    pass


def apply(config):
    # Initialize VPP control API
    vpp = VPPControl()

    if 'remove' in config:
        # Disable sFlow on all interfaces
        for interface in config.get('effective', {}).get('interface', {}).get('interface', []):
            vpp.cli(f'set sflow disable-interface {interface}')
        return None

    # Configure sample rate if specified
    if 'sample_rate' in config:
        vpp.cli(f'set sflow sampling-rate {config["sample_rate"]}')

    # Configure interfaces
    if 'interface' in config:
        # Enable sFlow on specified interfaces
        for interface in config['interface'].get('interface', []):
            vpp.cli(f'set sflow enable-interface {interface}')

        # Disable sFlow on interfaces that were removed from config
        effective_interfaces = config.get('effective', {}).get('interface', {}).get('interface', [])
        if effective_interfaces:
            for interface in effective_interfaces:
                if interface not in config['interface'].get('interface', []):
                    vpp.cli(f'set sflow disable-interface {interface}')


if __name__ == '__main__':
    try:
        c = get_config()
        verify(c)
        generate(c)
        apply(c)
    except ConfigError as e:
        print(e)
        exit(1)
