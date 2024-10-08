"""
********************************************************************************
* Name: user_account
* Author: nswain
* Created On: April 03, 2018
* Copyright: (c) Aquaveo 2018
********************************************************************************
"""
# Django
from django.shortcuts import render
# Tethys core
from tethys_sdk.permissions import has_permission
# ATCore
from .mixins import AppUsersViewMixin
from ...services.app_users.decorators import active_user_required


class UserAccount(AppUsersViewMixin):
    """
    Controller for user_account page.

    GET: Render list of all organizations.
    DELETE: Delete and organization.
    """
    page_title = 'My Account'
    template_name = 'atcore/app_users/user_account.html'
    base_template = 'atcore/app_users/base.html'
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        """
        Route get requests.
        """
        return self._handle_get(request)

    @active_user_required()
    def _handle_get(self, request, *args, **kwargs):
        """
        Handle get requests.
        """
        _AppUser = self.get_app_user_model()
        _Organization = self.get_organization_model()
        make_session = self.get_sessionmaker()
        permissions_manager = self.get_permissions_manager()
        session = make_session()

        request_app_user = _AppUser.get_app_user_from_request(request, session)

        if not request_app_user:
            pass

        # Get organizations
        user_organizations = request_app_user.get_organizations(session, request, cascade=False)

        organizations = []
        for user_organization in user_organizations:
            organizations.append({
                'name': user_organization.name,
                'license': _Organization.LICENSES.get_display_name_for(user_organization.license)
            })

        # Get custom_permissions groups
        permissions_groups = permissions_manager.get_all_permissions_groups_for(
            request_app_user,
            as_display_name=True
        )
        context = self.get_base_context(request)
        context.update({
            'page_title': self.page_title,
            'base_template': self.base_template,
            'username': request_app_user.username,
            'user_role': request_app_user.get_role(display_name=True),
            'user_account_status': 'Active' if request_app_user.is_active else 'Disabled',
            'permissions_groups': permissions_groups,
            'organizations': organizations,
            'show_users_link': has_permission(request, 'modify_users'),
            'show_resources_link': has_permission(request, 'view_resources'),
            'show_organizations_link': has_permission(request, 'view_organizations')
        })

        session.close()

        return render(request, self.template_name, context)
