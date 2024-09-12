"""
********************************************************************************
* Name: workflow_tab.py
* Author: jakeymac
* Created On: September 9th, 2024
* Copyright: (c) Aquaveo 2021
********************************************************************************
"""
from tethys_sdk.gizmos import TethysGizmoOptions


class WorkflowTab(TethysGizmoOptions):
    """
    Workflow tab gizmo.
    """
    gizmo_name = 'workflow_tab'

    def __init__(self, workflows, display_name='Workflow Tab', name='workflow-tab', id='workflow-tab', **kwargs):
        """
        constructor

        Args:
            display_name(str): label for workflow tab control. Defaults to "Workflow Tab".
            name(str): name of the workflow tab control. Defaults to 'workflow-tab'.
            id(str): id for workflow tab control. No id assigned if not specified.
        """
        
        
        # Initialize parent
        super(WorkflowTab, self).__init__(**kwargs)

        self.workflow_cards = workflows
        
        self.display_name = display_name
        self.name = name
        self.id = id

    @staticmethod
    def get_gizmo_js():
        """
        JavaScript specific to gizmo.
        """
        return ('workflows/js/csrf.js', 'workflows/gizmos/workflows_tab/workflows_tab.js','workflows/gizmos/workflows_tab/delete_row.js', 'workflows/gizmos/workflows_tab/enable-tooltips.js')

    @staticmethod
    def get_gizmo_css():
        """
        CSS specific to gizmo .
        """
        return ('workflows/gizmos/workflows_tab/btn-fab.css', 'workflows/gizmos/workflows_tab/flat-modal.css', 'workflows/gizmos/workflows_tab/workflows.css')
    
    def get_workflows(self):
        pass
    

class NewWorkflowModal(TethysGizmoOptions):
    """
    Workflow modal gizmo.
    """
    gizmo_name = 'new_workflow_modal'

    def __init__(self, csrf_token, workflow_types, display_name='New Workflow Modal', name='new-workflow-modal', id='new-workflow-modal', **kwargs):
        """
        constructor

        Args:
            display_name(str): label for new workflow modal control. Defaults to "New Workflow Modal".
            name(str): name of the workflow modal control. Defaults to 'new-workflow-modal'.
            id(str): id for new workflow modal control. No id assigned if not specified.
        """
        
        
        # Initialize parent
        super(NewWorkflowModal, self).__init__(**kwargs)
        
        self.csrf_token = csrf_token
        self.workflow_types = workflow_types

        self.display_name = display_name
        self.name = name
        self.id = id

    @staticmethod
    def get_gizmo_js():
        """
        JavaScript specific to gizmo.
        """
        return ('workflows/gizmos/workflows_tab/delete_row.js', 'workflows/gizmos/workflows_tab/enable-tooltips.js', 'workflows/gizmos/workflows_tab/workflows_tab.js')

    @staticmethod
    def get_gizmo_css():
        """
        CSS specific to gizmo .
        """
        return ('workflows/gizmos/workflows_tab/btn-fab.css', 'workflows/gizmos/workflows_tab/flat-modal.css', 'workflows/gizmos/workflows_tab/workflows.css')
    
class DeleteWorkflowModal(TethysGizmoOptions):
    """
    Workflow modal gizmo.
    """
    gizmo_name = 'delete_workflow_modal'

    def __init__(self, display_name='Delete Workflow Modal', name='delete-workflow-modal', id='delete-workflow-modal', **kwargs):
        """
        constructor

        Args:
            display_name(str): label for delete workflow modal control. Defaults to "Delete Workflow Modal".
            name(str): name of the delete workflow modal control. Defaults to 'delete-workflow-modal'.
            id(str): id for delete workflow modal control. No id assigned if not specified.
        """
        
        
        # Initialize parent
        super(DeleteWorkflowModal, self).__init__(**kwargs)
        
        self.display_name = display_name
        self.name = name
        self.id = id

    @staticmethod
    def get_vendor_js():
        """
        JavaScript vendor libraries
        """
        return ()

    @staticmethod
    def get_vendor_css():
        """
        CSS vendor libraries
        """
        return ()