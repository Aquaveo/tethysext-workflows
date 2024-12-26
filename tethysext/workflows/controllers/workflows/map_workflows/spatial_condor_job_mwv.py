"""
********************************************************************************
* Name: spatial_input_mwv.py
* Author: nswain
* Created On: January 21, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import os
import json
import logging
from django.contrib import messages
from django.shortcuts import render, redirect
from tethys_sdk.gizmos import JobsTable
from .map_workflow_view import MapWorkflowView
from ....steps import JobStep
from ....services.workflow_manager.condor_workflow_manager import WorkflowCondorJobManager


log = logging.getLogger(f'tethys.{__name__}')


class JobStepMWV(MapWorkflowView):
    """
    Controller for a map workflow view requiring spatial input (drawing).
    """
    template_name = 'workflows/workflows/spatial_condor_job_mwv.html'
    valid_step_classes = [JobStep]
    previous_steps_selectable = True
    jobs_table_refresh_interval = int(os.getenv('JOBS_TABLE_REFRESH_INTERVAL', 30000))  # ms

    def process_step_options(self, request, session, context, current_step, previous_step, next_step):
        """
        Hook for processing step options (i.e.: modify map or context based on step options).

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            context(dict): Context object for the map view template.
            current_step(Step): The current step to be rendered.
            previous_step(Step): The previous step.
            next_step(Step): The next step.
        """
        # Turn off feature selection on model layers
        map_view = context['map_view']
        self.set_feature_selection(map_view=map_view, enabled=False)

        # get tabular data if any
        tabular_data = current_step.workflow.get_tabular_data_for_previous_steps(current_step, request, session)

        has_tabular_data = len(tabular_data) > 0
        # Save changes to map view and layer groups
        context.update({ 
            'has_tabular_data': has_tabular_data,
            'tabular_data': tabular_data,
        })

        # Note: new layer created by super().process_step_options will have feature selection enabled by default
        super().process_step_options(
            request=request,
            session=session,
            context=context,
            current_step=current_step,
            previous_step=previous_step,
            next_step=next_step
        )

    def on_get_step(self, request, session, workflow, current_step, previous_step, next_step,
                    *args, **kwargs):
        """
        Hook that is called at the beginning of the get request for a workflow step, before any other controller logic occurs.
            request(HttpRequest): The request.
            session(sqlalchemy.Session): the session.
            workflow(TethysWorkflow): The current workflow.
            current_step(Step): The current step to be rendered.
            previous_step(Step): The previous step.
            next_step(Step): The next step.
        Returns:
            None or HttpResponse: If an HttpResponse is returned, render that instead.
        """  # noqa: E501
        step_status = current_step.get_status()
        if step_status != current_step.STATUS_PENDING:
            return self.render_condor_jobs_table(
                request, session, workflow, current_step, previous_step, next_step
            )

    def render_condor_jobs_table(self, request, session, workflow, current_step, previous_step, next_step):
        """
        Render a condor jobs table showing the status of the current job that is processing.
            request(HttpRequest): The request.
            session(sqlalchemy.Session): the session.
            workflow(TethysWorkflow): The current workflow.
            current_step(Step): The current step to be rendered.
        Returns:
            HttpResponse: The condor job table view.
        """
        job_id = current_step.get_attribute('condor_job_id')
        app = self.get_app()
        job_manager = app.get_job_manager()
        step_job = job_manager.get_job(job_id=job_id)

        jobs_table = JobsTable(
            jobs=[step_job],
            column_fields=('description', 'creation_time', ),
            hover=True,
            striped=True,
            condensed=False,
            show_status=True,
            show_detailed_status=True,
            actions=['logs'],
            show_actions=True, # TODO look at this
            refresh_interval=self.jobs_table_refresh_interval,
        )

        # Build step cards
        steps = self.build_step_cards(request, workflow)

        # Get the current app
        step_url_name = self.get_step_url_name(request, workflow)


        context = {
            'workflow': workflow,
            'steps': steps,
            'current_step': current_step,
            'next_step': next_step,
            'previous_step': previous_step,
            'step_url_name': step_url_name,
            'next_title': self.next_title,
            'finish_title': self.finish_title,
            'previous_title': self.previous_title,
            'back_url': self.back_url,
            'nav_title': workflow.name,
            'nav_subtitle': workflow.DISPLAY_TYPE_SINGULAR,
            'description': workflow.description,
            'jobs_table': jobs_table,
            'base_template': self.base_template
        }

        return render(request, 'workflows/workflows/spatial_condor_jobs_table.html', context)

    def process_step_data(self, request, session, step, current_url, previous_url, next_url):
        """
        Hook for processing user input data coming from the map view. Process form data found in request.POST and request.GET parameters and then return a redirect response to one of the given URLs.

        Args:
            request(HttpRequest): The request.
            session(sqlalchemy.orm.Session): Session bound to the steps.
            step(Step): The step to be updated.
            current_url(str): URL to step.
            previous_url(str): URL to the previous step.
            next_url(str): URL to the next step.

        Returns:
            HttpResponse: A Django response.

        Raises:
            ValueError: exceptions that occur due to user error, provide helpful message to help user solve issue.
            RuntimeError: exceptions that require developer attention.
        """  # noqa: E501
        if 'next-submit' in request.POST:
            step.validate()

            status = step.get_status(step.ROOT_STATUS_KEY)

            if status != step.STATUS_COMPLETE:
                if status == step.STATUS_WORKING:
                    working_message = step.options.get(
                        'working_message',
                        'Please wait for the job to finish running before proceeding.'
                    )
                    messages.warning(request, working_message)
                elif status in (step.STATUS_ERROR, step.STATUS_FAILED):
                    error_message = step.options.get(
                        'error_message',
                        'The job did not finish successfully. Please press "Rerun" to try again.'
                    )
                    messages.error(request, error_message)
                else:
                    pending_message = step.options.get(
                        'pending_message',
                        'Please press "Run" to continue.'
                    )
                    messages.info(request, pending_message)

                return redirect(request.path)

        return super().process_step_data(request, session, step, current_url, previous_url, next_url)

    def run_job(self, request, session, workflow_id, step_id, *args, **kwargs):
        """
        Handle run-job-form requests: prepare and submit the condor job.
        """
        if 'run-submit' not in request.POST and 'rerun-submit' not in request.POST:
            return redirect(request.path)

        # Get the workflow from the id
        workflow = self.get_workflow(request, workflow_id, session)

        # Validate data if going to next step
        step = self.get_step(request, step_id, session)

        # Get options
        scheduler_name = step.options.get('scheduler', None)
        if not scheduler_name:
            raise RuntimeError('Improperly configured JobStep: no "scheduler" option supplied.')

        jobs = step.options.get('jobs', None)
        if not jobs:
            raise RuntimeError('Improperly configured JobStep: no "jobs" option supplied.')

        workflow_kwargs = step.options.get('workflow_kwargs', None)

        # Get map manager
        map_manager = self.get_map_manager(request)

        # Get GeoServer Connection Information
        gs_engine = map_manager.spatial_manager.gs_engine

        # Define the working directory
        app = self.get_app()
        working_directory = self.get_working_directory(request, app)

        # Setup the Condor Workflow
        condor_job_manager = WorkflowCondorJobManager(
            session=session,
            workflow_step=step,
            jobs=jobs,
            user=request.user,
            working_directory=working_directory,
            app=app,
            scheduler_name=scheduler_name,
            gs_engine=gs_engine,
            workflow=workflow,
            workflow_kwargs=workflow_kwargs,
        )

        # Serialize parameters from all previous steps into json
        serialized_params = self.serialize_parameters(step)

        # Write serialized params to file for transfer
        params_file_path = os.path.join(condor_job_manager.workspace, 'workflow_params.json')
        with open(params_file_path, 'w') as params_file:
            params_file.write(serialized_params)

        # Add parameter file to workflow input files
        condor_job_manager.input_files.append(params_file_path)

        # Prepare the job
        job_id = condor_job_manager.prepare()

        # Submit job
        condor_job_manager.run_job()

        # Update status of the workflow step
        step.set_status(step.ROOT_STATUS_KEY, step.STATUS_WORKING)
        step.set_attribute(step.ATTR_STATUS_MESSAGE, None)

        # Save the job id to the step for later reference
        step.set_attribute('condor_job_id', job_id)

        # Allow the step to track statuses on each "sub-job"
        step.set_attribute('condor_job_statuses', [])

        # Reset next steps
        step.workflow.reset_next_steps(step)

        session.commit()

        return redirect(request.path)

    
    @staticmethod
    def get_working_directory(request, app):
        """
        Derive the working directory for the workflow.

        Args:
             request(HttpRequest): Django request instance.
             app(TethysAppBase): App class or instance.

        Returns:
            str: Path to working directory for the workflow.
        """
        user_workspace = app.get_user_workspace(request.user)
        working_directory = user_workspace.path
        return working_directory

    @staticmethod
    def serialize_parameters(step):
        """
        Serialize parameters from previous steps into a file for sending with the workflow.

        Args:
            step(Step): The current step.

        Returns:
            str: path to the file containing serialized parameters.
        """
        parameters = {}
        previous_steps = step.workflow.get_previous_steps(step)

        for previous_step in previous_steps:
            parameters.update({previous_step.name: previous_step.to_dict()})

        return json.dumps(parameters)

