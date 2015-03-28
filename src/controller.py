# Copyright 2011, Thomas G. Dimiduk
#
# This file is part of GroupEng.
#
# GroupEng is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GroupEng is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with GroupEng.  If not, see <http://www.gnu.org/licenses/>.

import time
import os
from operator import attrgetter
from .group import make_initial_groups
from .utility import mean, std
from .rule import make_rule, apply_rules_list, Balance, Distribute
from .student import load_classlist
from .course import Course
from . import input_parser



class InputDeckError(Exception):
    def __init__(self, e):
        self.e = e
    def __str__(self):
        return "You have a typo in your input deck.  Here is the error I got, \
see if it helps:\n{0}".format(self.e)

class UnevenGroups(Exception):
    pass

def run(input_deck):
    """
    Run GroupEng as specified by input_deck

    Parameters
    ----------
    input_deck: filename
        Input file specifying class information and grouping rules

    Output
    ------
    Output files determined by Input deck
    """
    dek = input_parser.read_input(input_deck)

    students = load_classlist(dek['classlist'], dek.get('student_identifier'))
    identifier = students[0].identifier
    course = Course(students, dek['group_size'], dek.get('uneven_size'))

    rules = [make_rule(r, course) for r in dek['rules']]

    balance_rules = filter(lambda x: isinstance(x, Balance), rules)

    groups = make_initial_groups(course, balance_rules)

    # Add a rule to distribute phantoms to avoid having more than one phantom
    # per group, put it first so that it is highest priority
    # we have to add this after the phantoms are created by
    # group.make_initial_groups so that it can see the phantoms
    rules = [Distribute(identifier, course, 'phantom')] + rules

    suceeded = apply_rules_list(rules, groups, course.students)

    groups.sort(key = attrgetter('group_number'))


    def failures(r):
        return sum(1- r.check(g) for g in groups)

    if failures(rules[0]) !=  0:
        raise UnevenGroups()

    # now get rid of the phantoms so they don't affect the output
    for group in groups:
        group.students = [s for s in group.students if s.data[identifier] !=
                          'phantom']

    course.students = [s for s in course.students if s.data[identifier] != 'phantom']

    ############################################################################
    # Output
    ############################################################################

    run_name = os.path.splitext(input_deck)[0]

    outdir = 'groups_{0}_{1}'.format(run_name,
                                     time.strftime('%Y-%m-%d_%H-%M-%S'))

    os.mkdir(outdir)
    os.chdir(outdir)

    def outfile(o):
        return open('{0}_{1}'.format(run_name,o),'w')

    group_output(groups, outfile('groups.csv'), identifier)
    group_output(groups, outfile('groups.txt'), identifier, sep = '\n')
    student_full_output(course.students, identifier, outfile('classlist.csv'))
    student_augmented_output(students, rules, outfile('details.csv'))


    report = outfile('statistics.txt')

    report.write('Ran GroupEng on: {0} with students from {1}\n\n'.format(
            input_deck, dek['classlist']))

    report.write('Made {0} groups\n\n'.format(len(groups)))

    for r in rules[1:]:
        n_fail = failures(r)
        if isinstance(r, Balance):
            group_means = sorted([mean(g, r.get_strength) for g in groups])
            attr = r.attribute
            report.write('{0} groups failed:'.format(n_fail))
            report.write('{0}: '.format(r))
            report.write('Class {0} Mean: {1:3.2f}, '.format(
                    attr, mean(students, r.get_strength)))
            report.write('Class {0} Std Dev: {1:3.2f}, '.format(
                        attr, std(students, r.get_strength)))
            report.write('Std Dev of Group {0} Means: {1:3.2f}'.format(
                    attr, std(group_means)))
            report.write('\n\n')
        else:
            report.write('{0} groups failed: {1}\n\n'.format(n_fail, r))

    report.write('Group Summaries\n')
    report.write('---------------\n')

    for g in groups:
        report.write('Group {0}: '.format(g.group_number))
        items = []
        for r in balance_rules:
            items.append('<{0} Mean: {1:3.2f}>'.format(
                    r.attribute, mean(g, r.get_strength)))
        for r in rules:
            if not r.check(g):
                items.append('Failed {0}'.format(r))
        report.write(', '.join(items))
        report.write('\n')

    report.write('\n')

    os.chdir('..')

    return groups, suceeded, outdir

def group_output(groups, outf, identifier, sep = ', '):
    groups.sort(key = lambda x: x.group_number)
    for g in groups:
        students = sorted(g.students, key = lambda x: x[identifier])
        outf.write('Group {0}{1}{2}\n'.format(g.group_number, sep,
                                             sep.join([str(s[identifier]) for s in
                                                       students])))

def student_full_output(students, identifier, outf):
    outf.write(', '.join(students[0].headers)+'\n')
    for s in students:
        outf.write(s.full_record()+'\n')


def student_augmented_output(students, rules, outf):
    outf.write(', '.join(students[0].headers))
    add_headers = ['']
    balance_rules = [r for r in rules if r.name == 'Balance']
    add_headers += ["group {0} mean".format(r.attribute) for r in balance_rules]
    add_headers += ["Rules Broken"]
    outf.write(', '.join(add_headers))
    outf.write('\n')
    group_number = 1
    num_student_headers = len(students[0].headers)
    students = sorted(students, key=attrgetter('group_number'))
    for i, s in enumerate(students):
        # write out a summary of the previous group if we have gone to the next
        # group
        if s.group_number != group_number:
            group = students[i-1].group
            outf.write("summary")
            outf.write(', ' * num_student_headers)
            summary = []
            summary += [str(mean(group.students, r.get_strength)) for r in balance_rules]
            summary += ["{}: {}".format(r.name, r.attribute) for r in rules if
                        not r.check(group.students)]
            outf.write(', '.join(summary))
            outf.write('\n\n')
            group_number = s.group_number

        outf.write(s.full_record()+'\n')
