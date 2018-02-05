#!/usr/bin/python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import time
import signal
import shutil
import argparse
import requests
import tempfile
import os.path
import subprocess


class BColors:
    COLOR_BLUE = '\033[94m'
    COLOR_RED_BG = '\033[101m'
    COLOR_RED = '\033[91m'
    COLOR_GREEN = '\033[92m'
    COLOR_BOLD = '\033[1m'
    COLOR_ENDC = '\033[0m'

    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Patcher:
    apk_file_path = None
    apk_tmp_dir = None

    VERBOSITY_LOW = 1   # only 'error' and 'done' messages
    VERBOSITY_MID = 2   # 'adding' messages too
    VERBOSITY_HIGH = 3  # all messages
    VERBOSITY = VERBOSITY_LOW

    ARCH_ARM = 'arm'
    ARCH_ARM64 = 'arm64'
    ARCH_X86 = 'x86'
    ARCH_X64 = 'x64'

    DEFAULT_GADGET_NAME = 'libfrida-gadget.so'
    DEFAULT_CONFIG_NAME = 'libfrida-gadget.config.so'
    DEFAULT_HOOKFILE_NAME = 'libhook.js.so'

    CONFIG_BIT = 1 << 0
    AUTOLOAD_BIT = 1 << 1

    INTERNET_PERMISSION = 'android.permission.INTERNET'

    def __init__(self, apk_file_path=None):
        self.apk_file_path = apk_file_path

    def set_verbosity(self, verbosity_level):
        self.VERBOSITY = verbosity_level

    def print_info(self, msg):
        if self.VERBOSITY >= self.VERBOSITY_HIGH:
            sys.stdout.write(BColors.COLOR_BLUE + '[*] {0}\n'.format(msg) + BColors.ENDC)

    def print_done(self, msg):
        if self.VERBOSITY >= self.VERBOSITY_LOW:
            sys.stdout.write(BColors.COLOR_GREEN + '[+] {0}\n'.format(msg) + BColors.ENDC)

    def print_warn(self, msg):
        if self.VERBOSITY >= self.VERBOSITY_LOW:
            sys.stdout.write(BColors.COLOR_RED + '[-] {0}\n'.format(msg) + BColors.ENDC)

    def has_satisfied_dependencies(self, action='all'):
        flag = True
        self.print_info('Checking dependencies...')

        # Check Frida
        try:
            subprocess.check_output(['frida', '--version'])
        except Exception:
            flag = False
            self.print_warn('Frida is not installed')

        # Check aapt
        if action in ['all']:
            try:
                subprocess.check_output(['aapt', 'version'])
            except Exception:
                flag = False
                self.print_warn('aapt is not installed')

        # Check apktool
        if action in ['all']:
            try:
                subprocess.check_output(['apktool', '--version'])
            except Exception:
                self.print_warn('Apktool is not installed')
                flag = False

        # Check unxz
        if action in ['all']:
            try:
                subprocess.check_output(['unxz', '--version'])
            except Exception:
                flag = False
                self.print_warn('unxz is not installed')

        # Check Zipalign
        if action in ['all']:
            cmd_output = subprocess.check_output(['zipalign;echo'],
                                                 stderr=subprocess.STDOUT, shell=True).decode('utf-8')

            if 'zip alignment' not in cmd_output.lower():
                flag = False
                self.print_warn('zipalign is not installed')

        return flag

    def update_apkpatcher_gadgets(self):
        if not self.has_satisfied_dependencies():
            self.print_warn('One or more dependencies are missing!')
            return False

        self.print_info('Updating frida gadgets')
        frida_version = subprocess.check_output(['frida', '--version']).decode('utf-8').strip()
        self.print_info('Frida version: {0}'.format(frida_version))

        github_link = 'https://api.github.com/repos/frida/frida/releases'

        response = requests.get(github_link).text
        releases = json.loads(response)

        release_link = None

        for release in releases:
            if release['tag_name'] == frida_version:
                release_link = release['url']
                break

        response = requests.get(release_link).text
        release_content = json.loads(response)

        assets = release_content['assets']

        list_gadgets = []
        for asset in assets:
            if 'gadget' in asset['name'] and 'android' in asset['name']:
                gadget = dict()
                gadget['name'] = asset['name']
                gadget['url'] = asset['browser_download_url']

                list_gadgets.append(gadget)

        current_folder = os.path.dirname(os.path.abspath(__file__))
        gadgets_folder = os.path.join(current_folder, 'gadgets')
        target_folder = os.path.join(gadgets_folder, frida_version)

        if not os.path.isdir(target_folder):
            os.makedirs(target_folder)

        downloaded_files = []
        for gadget in list_gadgets:
            gadget_file_path = os.path.join(target_folder, gadget['name'])

            if os.path.isfile(gadget_file_path.replace('.xz', '')):
                self.print_info('{0} already exists. Skipping.'.format(gadget['name']))
            else:
                self.download_file(gadget['url'], gadget_file_path)
                downloaded_files.append(gadget_file_path)

        self.print_info('Extracting downloaded files...')

        for downloaded_file in downloaded_files:
            subprocess.check_output(['unxz', downloaded_file])

        self.print_done('Done! Gadgets were updated')

        return True

    def download_file(self, url, target_path):
        file_name = target_path.split('/')[-1]
        response = requests.get(url, stream=True)
        total_length = response.headers.get('content-length')
        total_length = int(total_length)

        with open(target_path, 'wb') as f:
            downloaded = 0

            if self.VERBOSITY >= self.VERBOSITY_HIGH:
                sys.stdout.write('\r{0}[+] Downloading {1} - 000 %%{2}'
                                 .format(BColors.COLOR_BLUE, file_name, BColors.COLOR_ENDC))

                sys.stdout.flush()

            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    downloaded += len(chunk)
                    percentage = int(downloaded * 100 / total_length)

                    if self.VERBOSITY >= self.VERBOSITY_HIGH:
                        sys.stdout.write('\r{0}[+] Downloading {1} - {2:03d} %%{3}'
                                         .format(BColors.COLOR_BLUE, file_name, percentage, BColors.COLOR_ENDC))

                        sys.stdout.flush()

                    f.write(chunk)

        if self.VERBOSITY >= self.VERBOSITY_HIGH:
            sys.stdout.write('\n')

    def get_recommended_gadget(self):
        ret = None

        self.print_info('Trying to identify the right frida-gadget...')
        self.print_info('Waiting for device...')
        os.system('adb wait-for-device')
        abi = subprocess.check_output(['adb', 'shell', 'getprop ro.product.cpu.abi']).decode('utf-8').strip()

        self.print_info('The abi is {0}'.format(abi))

        frida_version = subprocess.check_output(['frida', '--version']).strip().decode('utf-8')
        current_folder = os.path.dirname(os.path.abspath(__file__))
        gadgets_folder = os.path.join(current_folder, 'gadgets')
        target_folder = os.path.join(gadgets_folder, frida_version)

        if os.path.isdir(target_folder):
            dir_list = os.listdir(target_folder)
            gadget_files = [f for f in dir_list if os.path.isfile(os.path.join(target_folder, f))]
        else:
            self.print_warn('Gadget folder not found. Try "python {0} --update"'.format(sys.argv[0]))
            return ret

        if abi in ['armeabi', 'armeabi-v7a']:
            for gadget_file in gadget_files:
                if 'arm' in gadget_file and '64' not in gadget_file:
                    full_path = os.path.join(target_folder, gadget_file)
                    ret = full_path
                    break

        elif abi is 'arm64-v8a' or 'arm64' in abi:
            for gadget_file in gadget_files:
                if 'arm64' in gadget_file:
                    full_path = os.path.join(target_folder, gadget_file)
                    ret = full_path
                    break

        elif abi is 'x86':
            for gadget_file in gadget_files:
                if 'i386' in gadget_file:
                    full_path = os.path.join(target_folder, gadget_file)
                    ret = full_path
                    break

        elif abi is 'x86_64':
            for gadget_file in gadget_files:
                if 'x86_64' in gadget_file:
                    full_path = os.path.join(target_folder, gadget_file)
                    ret = full_path
                    break

        if ret is None:
            self.print_warn('No recommended gadget file was found.')
        else:
            self.print_info('Architecture identified ({0}). Gadget was selected.' .format(abi))

        return ret

    def extract_apk(self, apk_path, destination_path, extract_resources=True):
        if extract_resources:
            self.print_info('Extracting {0} (with resources) to {1}'.format(apk_path, destination_path))
            self.print_info('Some errors may occur while decoding resources that have framework dependencies')

            subprocess.check_output(['apktool', 'd', '-o', destination_path, apk_path, '-f'])
        else:
            self.print_info('Extracting {0} (without resources) to {1}'.format(apk_path, destination_path))
            subprocess.check_output(['apktool', '-r', 'd', '-o', destination_path, apk_path, '-f'])

    def has_permission(self, apk_path, permission_name):
        permissions = subprocess.check_output(['aapt', 'dump', 'permissions', apk_path]).decode('utf-8')

        if permission_name in permissions:
            self.print_info('The app {0} has the permission "{1}"'.format(apk_path, permission_name))
            return True
        else:
            self.print_info("The app {0} doesn't have the permission '{1}'".format(apk_path, permission_name))
            return False

    def get_entrypoint_class_name(self, apk_path):
        dump_lines = subprocess.check_output(['aapt', 'dump', 'badging', apk_path]).decode('utf-8').split('\n')
        entrypoint_class = None

        for line in dump_lines:
            if 'launchable-activity:' in line:
                name_start = line.find('name=')
                entrypoint_class = line[name_start:].split(' ')[0]\
                    .replace('name=', '').replace('\'', '').replace('"', '')

                break

        if entrypoint_class is None:
            self.print_warn('Something was wrong while getting launchable-activity')

        return entrypoint_class

    def get_entrypoint_smali_path(self, base_path, entrypoint_class):
        files_at_path = os.listdir(base_path)
        entrypoint_final_path = None

        for file in files_at_path:
            if file.startswith('smali'):
                entrypoint_tmp = os.path.join(base_path, file, entrypoint_class.replace('.', '/') + '.smali')

                if os.path.isfile(entrypoint_tmp):
                    entrypoint_final_path = entrypoint_tmp
                    break

        if entrypoint_final_path is None:
            self.print_warn('Couldn\'t find the application entrypoint')
        else:
            self.print_info('Found application entrypoint at {0}'.format(entrypoint_final_path))

        return entrypoint_final_path

    def create_temp_folder_for_apk(self, apk_path):
        system_tmp_dir = tempfile.gettempdir()
        apkpatcher_tmp_dir = os.path.join(system_tmp_dir, 'apkpatcher_tmp')

        apk_name = apk_path.split('/')[-1]

        final_tmp_dir = os.path.join(apkpatcher_tmp_dir, apk_name.replace('.apk', '').replace('.', '_'))

        if os.path.isdir(final_tmp_dir):
            self.print_info('App temp dir already exists. Removing it...')
            shutil.rmtree(final_tmp_dir)

        os.makedirs(final_tmp_dir)

        return final_tmp_dir

    def insert_frida_loader(self, entrypoint_smali_path, frida_lib_name='frida-gadget'):
        partial_injection_code = '''
    const-string v0, "<LIBFRIDA>"

    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

        '''.replace('<LIBFRIDA>', frida_lib_name)

        full_injection_code = '''
.method static constructor <clinit>()V
    .locals 1

    .prologue
    const-string v0, "<LIBFRIDA>"

    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    return-void
.end method
        '''.replace('<LIBFRIDA>', frida_lib_name)

        with open(entrypoint_smali_path, 'r') as smali_file:
            content = smali_file.read()

            if 'frida-gadget' in content:
                self.print_info('The frida-gadget is already in the entrypoint. Skipping...')
                return False

            direct_methods_start_index = content.find('# direct methods')
            direct_methods_end_index = content.find('# virtual methods')

            if direct_methods_start_index is -1 or direct_methods_end_index is -1:
                self.print_warn('Could not find direct methods.')
                return False

            class_constructor_start_index = content.find('.method static constructor <clinit>()V',
                                                         direct_methods_start_index, direct_methods_end_index)

            if class_constructor_start_index is -1:
                has_class_constructor = False
            else:
                has_class_constructor = True

            class_constructor_end_index = -1
            if has_class_constructor:
                class_constructor_end_index = content.find('.end method',
                                                           class_constructor_start_index, direct_methods_end_index)

            if has_class_constructor and class_constructor_end_index is -1:
                self.print_warn('Could not find the end of class constructor.')
                return False

            prologue_start_index = -1
            if has_class_constructor:
                prologue_start_index = content.find('.prologue',
                                                    class_constructor_start_index, class_constructor_end_index)

            if has_class_constructor and prologue_start_index is -1:
                self.print_warn('Could not find the .prologue of class constructor.')
                return False

            prologue_end_index = -1
            if has_class_constructor and prologue_start_index > -1:
                prologue_end_index = prologue_start_index + len('.prologue') + 1

            if has_class_constructor:
                new_content = content[0:prologue_end_index]
                new_content += partial_injection_code
                new_content += content[prologue_end_index:]
            else:
                tmp_index = direct_methods_start_index + len('# direct methods') + 1
                new_content = content[0:tmp_index]
                new_content += full_injection_code
                new_content += content[tmp_index:]

        # The newContent is ready to be saved

        with open(entrypoint_smali_path, 'w') as smali_file:
            smali_file.write(new_content)

        self.print_info('Frida loader was injected in the entrypoint smali file!')

        return True

    def get_arch_by_gadget(self, gadget_path):
        if 'arm' in gadget_path and '64' not in gadget_path:
            return self.ARCH_ARM

        elif 'arm64' in gadget_path:
            return self.ARCH_ARM64

        elif 'i386' in gadget_path or ('x86' in gadget_path and '64' not in gadget_path):
            return self.ARCH_X86

        elif 'x86_64' in gadget_path:
            return self.ARCH_X64

        else:
            return None

    def create_lib_arch_folders(self, base_path, arch):
        sub_dir = None
        sub_dir_2 = None

        libs_path = os.path.join(base_path, 'lib/')

        if not os.path.isdir(libs_path):
            self.print_info('There is no "lib" folder. Creating...')
            os.makedirs(libs_path)

        if arch == self.ARCH_ARM:
            sub_dir = os.path.join(libs_path, 'armeabi')
            sub_dir_2 = os.path.join(libs_path, 'armeabi-v7a')

        elif arch == self.ARCH_ARM64:
            sub_dir = os.path.join(libs_path, 'arm64-v8a')

        elif arch == self.ARCH_X86:
            sub_dir = os.path.join(libs_path, 'x86')

        elif arch == self.ARCH_X64:
            sub_dir = os.path.join(libs_path, 'x86_64')

        else:
            self.print_warn("Couldn't create the appropriate folder with the given arch.")
            return []

        if not os.path.isdir(sub_dir):
            self.print_info('Creating folder {0}'.format(sub_dir))
            os.makedirs(sub_dir)

        if arch == self.ARCH_ARM:
            if not os.path.isdir(sub_dir_2):
                self.print_info('Creating folder {0}'.format(sub_dir_2))
                os.makedirs(sub_dir_2)

        if arch == self.ARCH_ARM:
            return [sub_dir, sub_dir_2]

        else:
            return [sub_dir]

    def delete_existing_gadget(self, arch_folder, delete_custom_files=0):
        gadget_path = os.path.join(arch_folder, self.DEFAULT_GADGET_NAME)

        if os.path.isfile(gadget_path):
            os.remove(gadget_path)

        if delete_custom_files:
            config_file_path = os.path.join(arch_folder, self.DEFAULT_CONFIG_NAME)
            hookfile_path = os.path.join(arch_folder, self.DEFAULT_HOOKFILE_NAME)

            os.remove(config_file_path)
            os.remove(hookfile_path)

    def insert_frida_lib(self, base_path, gadget_path, config_file_path=None, auto_load_script_path=None):
        arch = self.get_arch_by_gadget(gadget_path)
        arch_folders = self.create_lib_arch_folders(base_path, arch)

        if not arch_folders:
            self.print_warn('Some error occurred while creating the libs folders')
            return False

        for folder in arch_folders:
            if config_file_path and auto_load_script_path:
                self.delete_existing_gadget(folder, delete_custom_files=self.CONFIG_BIT | self.AUTOLOAD_BIT)

            elif config_file_path and not auto_load_script_path:
                self.delete_existing_gadget(folder, delete_custom_files=self.CONFIG_BIT)

            elif auto_load_script_path and not config_file_path:
                self.delete_existing_gadget(folder, delete_custom_files=self.AUTOLOAD_BIT)

            else:
                self.delete_existing_gadget(folder, delete_custom_files=0)

            target_gadget_path = os.path.join(folder, self.DEFAULT_GADGET_NAME)

            self.print_info('Copying gadget to {0}'.format(target_gadget_path))

            shutil.copyfile(gadget_path, target_gadget_path)

            if config_file_path:
                target_config_path = target_gadget_path.replace('.so', '.config.so')
                shutil.copyfile(config_file_path, target_config_path)

            if auto_load_script_path:
                target_autoload_path = target_gadget_path.replace(self.DEFAULT_GADGET_NAME, self.DEFAULT_HOOKFILE_NAME)
                shutil.copyfile(auto_load_script_path, target_autoload_path)

        return True

    def repackage_apk(self, base_apk_path, apk_name, target_file=None):
        if target_file is None:
            current_path = os.getcwd()
            target_file = os.path.join(current_path, apk_name.replace('.apk', '_patched.apk'))

            if os.path.isfile(target_file):
                timestamp = str(time.time()).replace('.', '')
                new_file_name = target_file.replace('.apk', '_{0}.apk'.format(timestamp))
                target_file = new_file_name

        self.print_info('Repackaging apk to {0}'.format(target_file))
        self.print_info('This may take some time...')

        subprocess.check_output(['apktool', 'b', '-o', target_file, base_apk_path])

        return target_file

    def inject_permission_manifest(self, base_dir, permission):
        self.print_info('Injecting permission {0} in Manifest...'.format(permission))

        permission_tag = '<uses-permission android:name="{0}"/>'.format(permission)
        manifest_path = os.path.join(base_dir, 'AndroidManifest.xml')

        f = open(manifest_path, 'r')
        manifest_content = f.read()
        f.close()

        start_manifest_tag = manifest_content.find('<manifest ')

        if start_manifest_tag is -1:
            self.print_warn('Something wrong with Manifest file')

            return False

        end_manifest_tag = manifest_content.find('>', start_manifest_tag)

        if end_manifest_tag is -1:
            self.print_warn('Something wrong with Manifest file')

            return False

        new_manifest = manifest_content[:end_manifest_tag + 1] + '\n'
        new_manifest += '    '  # indent
        new_manifest += permission_tag
        new_manifest += manifest_content[end_manifest_tag + 1:]

        f = open(manifest_path, 'w')
        f.write(new_manifest)
        f.close()

    def sign_and_zipalign(self, apk_path):
        self.print_info('Generating a random key...')
        subprocess.call(
            'keytool -genkey -keyalg RSA -keysize 2048 -validity 700 -noprompt -alias apkpatcheralias1 -dname '
            '"CN=apk.patcher.com, OU=ID, O=APK, L=Patcher, S=Patch, C=BR" -keystore apkpatcherkeystore '
            '-storepass password -keypass password',
            shell=True)

        self.print_info('Signing the patched apk...')
        subprocess.call(
            'jarsigner -sigalg SHA1withRSA -digestalg SHA1 -keystore apkpatcherkeystore '
            '-storepass password {0} apkpatcheralias1 >/dev/null 2>&1'.format(apk_path),
            shell=True)

        os.remove('apkpatcherkeystore')

        self.print_info('The apk was signed!')
        self.print_info('Optimizing with zipalign...')

        tmp_target_file = apk_path.replace('.apk', '_tmp.apk')
        shutil.move(apk_path, tmp_target_file)

        subprocess.call('zipalign 4 {0} {1}'.format(tmp_target_file, apk_path), stderr=subprocess.STDOUT, shell=True)

        os.remove(tmp_target_file)

        self.print_info('The file was optimized!')

    @staticmethod
    def get_default_config_file():
        config = '''
{
    "interaction": {
        "type": "script",
        "path": "./libhook.js.so"
    }
}
            '''

        path = os.path.join(os.getcwd(), 'generatedConfigFile.config')
        f = open(path, 'w')

        f.write(config)
        f.close()

        return path


def signal_handler(_signal_id, _frame):
    print('\n' + BColors.COLOR_RED + 'YOU PRESSED CTRL+C! Exiting now...' + BColors.ENDC)

    sys.exit(1)


def main():
    patcher = Patcher()

    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--apk', help='Specify the apk you want to patch')
    parser.add_argument('-g', '--gadget', help='Specify the frida-gadget file')
    parser.add_argument('--verbosity', help='Verbosity level (1 to 3). Default is 3')
    parser.add_argument('--update', help='Update frida-gadgets', action='store_true')
    parser.add_argument('--force-resources', help='Force extract resources and manifest', action='store_true')
    parser.add_argument('-o', '--output-file', help='Specify the output file (patched)')

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()

        return 1

    if args.verbosity:
        patcher.set_verbosity(int(args.verbosity))
    else:
        patcher.set_verbosity(patcher.VERBOSITY_HIGH)

    if args.update:
        patcher.update_apkpatcher_gadgets()

        return 0

    if not args.apk:
        parser.print_help()

        return 1

    if not patcher.has_satisfied_dependencies('all'):
        patcher.print_warn('One or more dependencies were not satisfied.')

        return 1

    if args.gadget:
        gadget_to_use = args.gadget

    else:
        gadget_to_use = patcher.get_recommended_gadget()

    if gadget_to_use is None or not os.path.isfile(gadget_to_use):
        patcher.print_warn('Could not identify the gadget!')

        return

    # THE APK PATCHING STARTS HERE

    apk_file_path = args.apk
    temporary_path = patcher.create_temp_folder_for_apk(apk_file_path)
    has_internet_permission = patcher.has_permission(apk_file_path, patcher.INTERNET_PERMISSION)

    if not has_internet_permission or args.force_resources:
        patcher.extract_apk(apk_file_path, temporary_path, extract_resources=True)
    else:
        patcher.extract_apk(apk_file_path, temporary_path, extract_resources=False)

    if not has_internet_permission:
        patcher.inject_permission_manifest(temporary_path, patcher.INTERNET_PERMISSION)

    # START --[ INJECTING FRIDA LIB FILE AND SMALI CODE ]--
    entrypoint_class = patcher.get_entrypoint_class_name(apk_file_path)
    entrypoint_smali_path = patcher.get_entrypoint_smali_path(temporary_path, entrypoint_class)

    patcher.insert_frida_loader(entrypoint_smali_path)
    patcher.insert_frida_lib(temporary_path, gadget_to_use)
    # END --[ INJECTING FRIDA LIB FILE AND SMALI CODE ]--

    apk_file_name = apk_file_path.split('/')[-1]

    if args.output_file:
        output_file_path = patcher.repackage_apk(temporary_path, apk_file_name, target_file=args.output_file)

    else:
        output_file_path = patcher.repackage_apk(temporary_path, apk_file_name)

    patcher.sign_and_zipalign(output_file_path)

    patcher.print_done('Your file is located at {0}'.format(output_file_path))

    return 0

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()
