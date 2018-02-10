# -*- python -*-
# ex: set syntax=python:

from buildbot.plugins import *
import sys
import os
import bbconf

c = {}

vm_cpu_count = 8

mac_os_min_version = '10.11'
mac_os_sdks_path = '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs'

ngftp = 'ftp://192.168.255.51/software/installer'
siteftp = 'ftp://192.168.255.1/desktop'
ngftp_user = bbconf.ftp_mynextgis_user
siteftp_user = bbconf.ftp_upldsoft_user
upload_script_src = 'https://raw.githubusercontent.com/nextgis/buildbot/master/ftp_uploader.py'
upload_script_name = 'ftp_upload.py'
if_project_name = 'inst_framework'

installer_git = 'git://github.com/nextgis/nextgis_installer.git'

c['change_source'] = []
c['schedulers'] = []
c['builders'] = []

project_name = 'create_installer'

forceScheduler_create = schedulers.ForceScheduler(
                            name=project_name + "_update",
                            label="Update installer",
                            buttonName="Update installer",
                            builderNames=[
                                            project_name + "_win32",
                                            project_name + "_win64",
                                            project_name + "_mac",
                                        ],
                            properties=[util.StringParameter(name="force",
                                            label="Force update specified packages even not any changes exists:",
                                            default="all", size=280),
                                        util.StringParameter(name="suffix",
                                                        label="Installer name and URL path suffix (can be empty):",
                                                        default="-dev", size=40),
                                       ],
                        )
forceScheduler_update = schedulers.ForceScheduler(
                            name=project_name + "_create",
                            label="Create installer",
                            buttonName="Create installer",
                            builderNames=[
                                            project_name + "_win32",
                                            project_name + "_win64",
                                            project_name + "_mac",
                                        ],
                            properties=[util.StringParameter(name="suffix",
                                                            label="Installer name and URL path suffix (can be empty):",
                                                            default="-dev", size=40),
                                       ],
                        )
c['schedulers'].append(forceScheduler_create)
c['schedulers'].append(forceScheduler_update)

@util.renderer
def commandArgs(props):
    command = ''
    if props.getProperty('scheduler') ==  project_name + "_create":
        command = 'create'
    elif props.getProperty('scheduler') ==  project_name + "_update":
        command = 'update --force ' + props.getProperty('force')
    else:
        command = 'update'

    return command

platforms = [
    {'name' : 'win32', 'worker' : 'build-win'},
    {'name' : 'win64', 'worker' : 'build-win'},
    {'name' : 'mac', 'worker' : 'build-mac'} ]

# Create triggerable shcedulers
for platform in platforms:
    triggerScheduler = schedulers.Triggerable(
        name=project_name + "_" + platform['name'],
        builderNames=[ project_name + "_" + platform['name'], ])
    c['schedulers'].append(triggerScheduler)

# Create builders
for platform in platforms:
    code_dir_last = '{}_{}_code'.format('installer', platform['name'])
    code_dir = os.path.join('build', code_dir_last)
    build_dir_name = 'build'
    build_dir = os.path.join(code_dir, build_dir_name)

    factory = util.BuildFactory()

    factory.addStep(steps.Git(repourl=installer_git,
                               mode='full',
                               shallow=True,
                               method='clobber',
                               submodules=False,
                               alwaysUseLatest=True,
                               workdir=code_dir))

    factory.addStep(steps.MakeDirectory(dir=build_dir,
                                        name="Make build directory"))

    # 1. Get and unpack installer and qt5 static from ftp
    if_prefix = '_mac'
    separator = '/'
    env = {
        'PATH': [
                    "/usr/local/bin",
                    "${PATH}"
                ],
    }
    installer_ext = '.dmg'
    if 'win' in platform['name']:
        if_prefix = '_win'
        separator = '\\'
        env = {}
        installer_ext = '.exe'

    repo_name_base = 'repository-' + platform['name']
    repo_archive = 'repository-' + platform['name'] + '.zip'
    logfile = 'stdio'

    factory.addStep(steps.ShellSequence(commands=[
            util.ShellArg(command=["curl", '-u', ngftp_user, ngftp + '/src/' + if_project_name + if_prefix + '/package.zip', '-o', 'package.zip', '-s'], logfile=logfile),
            util.ShellArg(command=["cmake", '-E', 'tar', 'xzf', 'package.zip'], logfile=logfile),
        ],
        name="Download installer package",
        haltOnFailure=True,
        workdir=build_dir,
        env=env))
    factory.addStep(steps.CopyDirectory(src=build_dir + "/qtifw_build", dest=code_dir + "/qtifw_pkg"))
    factory.addStep(steps.RemoveDirectory(dir=build_dir + "/qtifw_build"))

    factory.addStep(steps.ShellSequence(commands=[
            util.ShellArg(command=["curl", '-u', ngftp_user, ngftp + '/src/' + if_project_name + if_prefix + '/qt/package.zip', '-o', 'package.zip', '-s'], logfile=logfile),
            util.ShellArg(command=["cmake", '-E', 'tar', 'xzf', 'package.zip'], logfile=logfile),
        ],
        name="Download qt package",
        haltOnFailure=True,
        workdir=build_dir,
        env=env))
    factory.addStep(steps.CopyDirectory(src=build_dir + "/inst", dest=code_dir + "/qt"))
    factory.addStep(steps.RemoveDirectory(dir=build_dir + "/inst"))

    # 2. Get repository from ftp
    factory.addStep(steps.ShellSequence(commands=[
            util.ShellArg(command=["curl", '-u', ngftp_user, ngftp + '/src/' + 'repo_' + platform['name'] + '/' + repo_archive, '-o', repo_archive, '-s'], logfile=logfile),
            util.ShellArg(command=["cmake", '-E', 'tar', 'xzf', repo_archive], logfile=logfile),
        ],
        name="Download repository",
        haltOnFailure=True,
        doStepIf=(lambda(step): step.getProperty("scheduler") != project_name + "_create"),
        workdir=build_dir,
        env=env))

    factory.addStep(steps.ShellCommand(command=["curl", '-u', ngftp_user, ngftp + '/src/' + 'repo_' + platform['name'] + '/versions.pkl', '-o', 'versions.pkl', '-s'],
                                        name="Download versions.pkl",
                                        haltOnFailure=True, # The repository may not be exists
                                        doStepIf=(lambda(step): step.getProperty("scheduler") != project_name + "_create"),
                                        workdir=code_dir,
                                        env=env))

    # 3. Get compiled libraries
    factory.addStep(steps.ShellCommand(command=["python", 'opt' + separator + 'create_installer.py',
                                                '-s', 'inst',
                                                '-q', 'qt/bin',
                                                '-t', build_dir_name,
                                                'prepare', '--ftp_user', ngftp_user,
                                                '--ftp', ngftp + '/src/',
                                                ],
                                           name="Prepare packages data",
                                           haltOnFailure=True,
                                           workdir=code_dir,
                                           env=env))
    # 4. Create or update repository
    # Install NextGIS sign sertificate
    if 'mac' == platform['name']:
        factory.addStep(steps.ShellCommand(command=['pip', 'install', '--user', 'dmgbuild'],
                                            name="Install dmgbuild python package",
                                            haltOnFailure=True,
                                            workdir=code_dir,
                                            env=env))

        factory.addStep(steps.FileDownload(mastersrc="/opt/buildbot/dev.p12",
                                            workerdest=code_dir_last + "/dev.p12",
                                            ))
        factory.addStep(steps.ShellSequence(commands=[
                util.ShellArg(command=['security', 'create-keychain', '-p', 'none', 'codesign.keychain'],
                              logfile=logfile,
                              haltOnFailure=False, flunkOnWarnings=False, flunkOnFailure=False,
                              warnOnWarnings=False, warnOnFailure=False),
                util.ShellArg(command=['security', 'default-keychain', '-s', 'codesign.keychain'], logfile=logfile),
                util.ShellArg(command=['security', 'unlock-keychain', '-p', 'none', 'codesign.keychain'], logfile=logfile),
                util.ShellArg(command=['security', 'import', './dev.p12', '-k', 'codesign.keychain', '-P', '', '-A'], logfile=logfile),
                util.ShellArg(command=['security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:', '-s', '-k', 'none', 'codesign.keychain',], logfile=logfile),
            ],
            name="Install NextGIS sign sertificate",
            haltOnFailure=True,
            workdir=code_dir,
            env=env))

    repo_url_base = 'http://nextgis.com/programs/desktop/repository-' + platform['name']
    installer_name_base = 'nextgis-setup-' + platform['name']
    factory.addStep(steps.ShellCommand(command=["python", 'opt' + separator + 'create_installer.py',
                                                '-s', 'inst',
                                                '-q', 'qt/bin',
                                                '-t', build_dir_name,
                                                '-n', '-r', util.Interpolate('%(kw:url)s%(prop:suffix)s', url=repo_url_base),
                                                '-i', util.Interpolate('%(kw:basename)s%(prop:suffix)s', basename=installer_name_base),
                                                util.Interpolate('%(kw:ca)s', ca=commandArgs),
                                                ],
                                        name="Create/Update repository",
                                        haltOnFailure=True,
                                        workdir=code_dir,
                                        env=env))

    # 5. Upload installer to ftp
    factory.addStep(steps.ShellCommand(command=["curl", '-u', ngftp_user, '-T',
                                        util.Interpolate('%(kw:basename)s%(prop:suffix)s' + installer_ext,
                                                        basename=installer_name_base),
                                        '-s', '--ftp-create-dirs', ngftp],
                                       name="Upload installer to ftp",
                                       haltOnFailure=True,
                                       doStepIf=(lambda(step): step.getProperty("scheduler") == project_name + "_create"),
                                       workdir=build_dir,
                                       env=env))

    # 6. Create zip from repository
    factory.addStep(steps.ShellCommand(command=["cmake", '-E', 'tar', 'cfv', repo_archive, '--format=zip',
                                        util.Interpolate('%(kw:basename)s%(prop:suffix)s',
                                            basename=repo_name_base)],
                                        name="Create zip from repository",
                                        haltOnFailure=True,
                                        workdir=build_dir,
                                        env=env))

    # 7. Upload repository archive to ftp
    factory.addStep(steps.ShellCommand(command=["curl", '-u', ngftp_user, '-T',
                                        repo_archive, '-s', '--ftp-create-dirs',
                                        ngftp + '/src/' + 'repo_' + platform['name'],],
                                       name="Upload repository archive to ftp",
                                       haltOnFailure=True,
                                       workdir=build_dir,
                                       env=env))
    factory.addStep(steps.ShellCommand(command=["curl", '-u', ngftp_user, '-T',
                                        'versions.pkl', '-s', '--ftp-create-dirs',
                                        ngftp + '/src/' + 'repo_' + platform['name'],],
                                       name="Upload versions.pkl to ftp",
                                       haltOnFailure=True,
                                       workdir=code_dir,
                                       env=env))

    # 8. Upload repository archive to site
    factory.addStep(steps.ShellCommand(command=["curl", '-u', siteftp_user, '-T',
                                        repo_archive, '-s', '--ftp-create-dirs', siteftp],
                                       name="Upload repository archive to site",
                                       haltOnFailure=True,
                                       workdir=build_dir,
                                       env=env))

    builder = util.BuilderConfig(name = project_name + "_" + platform['name'],
                                 workernames = [platform['worker']],
                                 factory = factory,
                                 description="Create/update installer on " + platform['name'],)

    c['builders'].append(builder)
