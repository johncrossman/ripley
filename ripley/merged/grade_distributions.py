"""
Copyright ©2023. The Regents of the University of California (Regents). All Rights Reserved.

Permission to use, copy, modify, and distribute this software and its documentation
for educational, research, and not-for-profit purposes, without fee and without a
signed licensing agreement, is hereby granted, provided that the above copyright
notice, this paragraph and the following two paragraphs appear in all copies,
modifications, and distributions.

Contact The Office of Technology Licensing, UC Berkeley, 2150 Shattuck Avenue,
Suite 510, Berkeley, CA 94720-1620, (510) 643-7201, otl@berkeley.edu,
http://ipira.berkeley.edu/industry-info for commercial licensing opportunities.

IN NO EVENT SHALL REGENTS BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT, SPECIAL,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF
THE USE OF THIS SOFTWARE AND ITS DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.

REGENTS SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE
SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY, PROVIDED HEREUNDER IS PROVIDED
"AS IS". REGENTS HAS NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES,
ENHANCEMENTS, OR MODIFICATIONS.
"""

from copy import deepcopy
from itertools import groupby

from flask import current_app as app
from ripley.externals.data_loch import get_grades_with_demographics, get_grades_with_enrollments
from ripley.lib.berkeley_term import BerkeleyTerm
from ripley.lib.util import to_percentage


EMPTY_DEMOGRAPHIC_DISTRIBUTION = {
    'genders': {},
    'internationalStatus': {
        'true': 0,
        'false': 0,
    },
    'transferStatus': {
        'true': 0,
        'false': 0,
    },
    'underrepresentedMinorityStatus': {
        'true': 0,
        'false': 0,
    },
    'count': 0,
    'totalGradePoints': 0,
}


def get_grade_distributions(term_id, section_ids, instructor_uid):  # noqa
    demographics_distribution = {}
    grade_totals = {}
    grade_distribution_by_term = {}
    student_grades = get_grades_with_demographics(term_id, section_ids, instructor_uid)
    if len(student_grades) < int(app.config['NEWT_MINIMUM_CLASS_SIZE']):
        return False, False

    for row in student_grades:
        term_id = row['term_id']
        grade = row['grade']
        if grade:
            grade_points = GRADE_POINTS.get(grade, 0)
            if term_id not in demographics_distribution:
                demographics_distribution[term_id] = deepcopy(EMPTY_DEMOGRAPHIC_DISTRIBUTION)
                grade_totals[term_id] = deepcopy(EMPTY_DEMOGRAPHIC_DISTRIBUTION)
            demographics_distribution[term_id]['count'] += 1
            demographics_distribution[term_id]['totalGradePoints'] += grade_points
            demographics_distribution[term_id]['courseName'] = row['sis_course_name']

            def _count_boolean_value(column, distribution_key):
                if row[column]:
                    demographics_distribution[term_id][distribution_key]['true'] += grade_points
                    grade_totals[term_id][distribution_key]['true'] += 1
                else:
                    demographics_distribution[term_id][distribution_key]['false'] += grade_points
                    grade_totals[term_id][distribution_key]['false'] += 1

            _count_boolean_value('transfer', 'transferStatus')
            _count_boolean_value('minority', 'underrepresentedMinorityStatus')
            _count_boolean_value('visa_type', 'internationalStatus')

            def _count_string_value(value, distribution_key):
                value = str(value) if value else 'none'
                if value not in demographics_distribution[term_id][distribution_key]:
                    demographics_distribution[term_id][distribution_key][value] = 0
                if value not in grade_totals[term_id][distribution_key]:
                    grade_totals[term_id][distribution_key][value] = 0
                demographics_distribution[term_id][distribution_key][value] += grade_points
                grade_totals[term_id][distribution_key][value] += 1

            _count_string_value(_simplify_gender(row['gender']), 'genders')

            if term_id not in grade_distribution_by_term:
                grade_distribution_by_term[term_id] = {
                    'count': 0,
                }
            if grade not in grade_distribution_by_term[term_id]:
                grade_distribution_by_term[term_id][grade] = {
                    'count': 0,
                    'courseName': row['sis_course_name'],
                }
            grade_distribution_by_term[term_id][grade]['count'] += 1
            grade_distribution_by_term[term_id]['count'] += 1

    sorted_grade_distribution_by_term = {}
    for term_id, term_distribution in grade_distribution_by_term.items():
        sorted_grade_distribution = []
        sufficient_data = True
        for grade in sorted(term_distribution.keys(), key=_grade_ordering_index):
            if not sufficient_data:
                continue
            if grade in GRADE_ORDERING:
                if term_distribution[grade]['count'] < app.config['GRADE_DISTRIBUTION_MIN_STUDENTS_PER_CATEGORY']:
                    sufficient_data = False
                    app.logger.debug(f"Term ID {term_id} excluded from {term_distribution[grade]['courseName']} prior enrollment chart: \
only {term_distribution[grade]['count']} students with {grade}")
                    continue
                term_distribution[grade].update({
                    'classSize': term_distribution['count'],
                    'grade': grade,
                    'percentage': to_percentage(
                        term_distribution[grade]['count'],
                        term_distribution['count'],
                    ),
                })
                sorted_grade_distribution.append(term_distribution[grade])
        if sufficient_data:
            sorted_grade_distribution_by_term[term_id] = sorted_grade_distribution

    sorted_demographics_distribution = []
    for term_id in sorted(demographics_distribution.keys()):
        sufficient_data = True
        for distribution_key, values in demographics_distribution[term_id].items():
            if distribution_key in ['count', 'courseName', 'totalGradePoints'] or not sufficient_data:
                continue
            for distribution_value, total_grade_points in values.items():
                student_count = grade_totals[term_id][distribution_key][distribution_value]
                if student_count < app.config['GRADE_DISTRIBUTION_MIN_STUDENTS_PER_CATEGORY']:
                    app.logger.debug(f"Term ID {term_id} excluded from {demographics_distribution[term_id]['courseName']} demographics chart: \
only {student_count} {distribution_key}--{distribution_value} students")
                    sufficient_data = False
                    continue
                demographics_distribution[term_id][distribution_key][distribution_value] = {
                    'averageGradePoints': (total_grade_points / student_count) if student_count > 0 else 0,
                    'count': student_count,
                }
        if sufficient_data:
            term_student_count = demographics_distribution[term_id]['count']
            term_total_grade_points = demographics_distribution[term_id].pop('totalGradePoints', 0)
            sorted_demographics_distribution.append({
                'averageGradePoints': (term_total_grade_points / term_student_count) if term_student_count > 0 else 0,
                **demographics_distribution[term_id],
                'termId': term_id,
                'termName': BerkeleyTerm.from_sis_term_id(term_id).to_english(),
            })
    return sorted_demographics_distribution, sorted_grade_distribution_by_term


def get_grade_distribution_with_prior_enrollments(term_id, course_name, instructor_uid, prior_course_name):
    distribution = {}
    for term_id, rows in groupby(
        get_grades_with_enrollments(term_id, course_name, instructor_uid, prior_course_name),
        key=lambda x: x['sis_term_id'],
    ):
        if term_id not in distribution:
            distribution[term_id] = {
                'count': 0,
                'total': 0,
            }
        for r in rows:
            if r['grade'] not in distribution[term_id]:
                distribution[term_id][r['grade']] = {
                    'count': 0,
                    'total': 0,
                }
            distribution[term_id][r['grade']]['count'] += r['has_prior_enrollment']
            distribution[term_id][r['grade']]['total'] += 1
            distribution[term_id]['count'] += r['has_prior_enrollment']
            distribution[term_id]['total'] += 1

    sorted_distributions = {}
    for term_id, term_distribution in distribution.items():
        total_prior_enroll_count = term_distribution['count']
        total_no_prior_enroll_count = term_distribution['total'] - total_prior_enroll_count
        sorted_distribution = []
        sufficient_data = total_prior_enroll_count > 0 and total_no_prior_enroll_count > 0
        for grade in sorted(term_distribution.keys(), key=_grade_ordering_index):
            if not sufficient_data:
                continue
            if grade in GRADE_ORDERING:
                grade_values = term_distribution.get(grade, {})
                grade_prior_enroll_count = grade_values.get('count', 0)
                total_grade_count = grade_values.get('total', 0)
                grade_no_prior_enroll_count = total_grade_count - grade_prior_enroll_count
                if total_grade_count < app.config['GRADE_DISTRIBUTION_MIN_STUDENTS_PER_CATEGORY']:
                    sufficient_data = False
                    continue
                sorted_distribution.append({
                    'classSize': term_distribution['total'],
                    'courseName': prior_course_name,
                    'grade': grade,
                    'noPriorEnrollCount': grade_no_prior_enroll_count,
                    'noPriorEnrollPercentage': to_percentage(grade_no_prior_enroll_count, total_no_prior_enroll_count),
                    'priorEnrollCount': grade_prior_enroll_count,
                    'priorEnrollPercentage': to_percentage(grade_prior_enroll_count, total_prior_enroll_count),
                    'termName': BerkeleyTerm.from_sis_term_id(term_id).to_english(),
                    'totalCount': total_grade_count,
                    'totalPercentage': to_percentage(total_grade_count, term_distribution['total']),
                })
        if sufficient_data:
            sorted_distributions[term_id] = sorted_distribution
    return sorted_distributions


GRADE_ORDERING = ('A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F', 'P', 'NP', 'I')


# Source: https://registrar.berkeley.edu/faculty-staff/grading/grading-policies-reports/
GRADE_POINTS = {
    'A+': 4,
    'A': 4,
    'A-': 3.7,
    'B+': 3.3,
    'B': 3,
    'B-': 2.7,
    'C+': 2.3,
    'C': 2,
    'C-': 1.7,
    'D+': 1.3,
    'D': 1,
    'D-': .7,
    'F': 0,
    'P': 0,
    'NP': 0,
    'I': 0,
}


def _grade_ordering_index(grade):
    try:
        return GRADE_ORDERING.index(grade)
    except ValueError:
        return len(GRADE_ORDERING)


def _simplify_gender(gender):
    if gender == 'Female':
        return 'female'
    elif gender == 'Male':
        return 'male'
    else:
        return 'other'
