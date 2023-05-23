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

from unittest import mock

import pytest
from ripley.jobs.refresh_bcourses_inactivate_job import RefreshBcoursesInactivateJob
from tests.util import assert_s3_key_not_found, read_s3_csv, setup_bcourses_refresh_job


class TestRefreshBcoursesInactivate:

    def test_no_changes(self, app):
        with setup_bcourses_refresh_job(app) as s3:
            RefreshBcoursesInactivateJob(app)._run()
            assert_s3_key_not_found(app, s3, 'sis-id-sis-import')
            assert_s3_key_not_found(app, s3, 'user-sis-import')

    def test_no_enrollments_in_inactivate_job(self, app):
        with setup_bcourses_refresh_job(app) as s3:
            RefreshBcoursesInactivateJob(app)._run()
            assert_s3_key_not_found(app, s3, 'enrollments-TERM-2023-B-sis-import')

    @mock.patch('ripley.jobs.refresh_bcourses_base_job.get_all_active_users')
    def test_vanishing_user(self, mock_all_users, app, campus_users):
        with setup_bcourses_refresh_job(app) as s3:
            ash = next(u for u in campus_users if u['ldap_uid'] == '30000')
            campus_users.remove(ash)
            mock_all_users.return_value = campus_users

            RefreshBcoursesInactivateJob(app)._run()

            sis_id_changes_imported = read_s3_csv(app, s3, 'sis-id-sis-import')
            assert len(sis_id_changes_imported) == 2
            assert sis_id_changes_imported[0] == 'old_id,new_id,old_integration_id,new_integration_id,type'
            assert sis_id_changes_imported[1] == '30030000,UID:30000,,,user'

            user_changes_imported = read_s3_csv(app, s3, 'user-sis-import')
            assert len(user_changes_imported) == 2
            assert user_changes_imported[0] == 'user_id,login_id,first_name,last_name,email,status'
            assert user_changes_imported[1] == 'UID:30000,30000,Ash,🤖,,suspended'

    @pytest.fixture(scope='function')
    def campus_users(self, app):
        from ripley.externals.data_loch import get_all_active_users
        return get_all_active_users()
