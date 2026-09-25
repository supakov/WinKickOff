# Safety

## Virtual machine first

Every new or modified answer file is first used for an installation on a virtual machine. Only after it
has been checked according to the "Installation and checks" document is the file used on work computers.
Installation erases the selected disk partition: on a computer with data, choose the partition carefully.

## Initial accounts without passwords

Admin (administrator) and User (standard user) are created without passwords. This is a deliberate
decision: passwords and groups are assigned by a separate project after installation. Until passwords
are assigned:

- User cannot confirm a User Account Control prompt with Admin's credentials (Windows does not accept
  a blank password anywhere except when signing in at the computer itself); programs are installed while
  signed in as Admin;
- shared folders between computers do not work: Windows does not allow network access with a blank password.

A password set in the program is written to the answer file in plain text. Keep such a file and the profile
secret. Copies of the answer file are deleted from the installed computer two minutes after the initial
setup.

## Risky rules

Rules with the "risky" level are highlighted in color in the tree, and the check (F7) warns
about each one that is enabled. Turning off rules with the "baseline" level also produces
a warning: they form the foundation of protection.

## Display language and keyboard layouts

The Windows display language is taken from the installation image and is not changed. The input languages
rule changes only each user's list of keyboard layouts at the first sign-in. If the keyboard layouts are
not as expected after the first sign-in, look at the `Setup-User.<name>.log` log and correct the list in
Windows Settings (the language section); this rule does not touch any other system settings.

## The computer that runs WinKickOff

The program changes nothing on the computer it runs on: it does not write to the registry, does not install
services and does not connect to the internet. All its files (profiles, built files, log, settings) are kept
in its own folder.
