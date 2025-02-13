"""
********************************************************************************
* Name: form_input_wv.py
* Author: mmlebaron, glarsen
* Created On: October 18, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import logging

from ..workflow_view import WorkflowView
from ....steps import FormInputStep
from ....forms.widgets.param_widgets import generate_django_form

from bokeh.embed import server_document

log = logging.getLogger(f'tethys.{__name__}')


class FormInputWV(WorkflowView):
    """
    Controller for FormInputRWV.
    """
    template_name = 'workflows/workflows/form_input_wv.html'
    valid_step_classes = [FormInputStep]

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
        # Status style
        form_title = current_step.options.get('form_title', current_step.name) or current_step.name

        
        package, p_class = current_step.options['param_class'].rsplit('.', 1)
        mod = __import__(package, fromlist=[p_class])
        ParamClass = getattr(mod, p_class)

        # Get the renderer option
        renderer = current_step.options['renderer']
        context.update({'renderer': renderer})

        # Django Renderer
        if renderer == 'django':
            p = ParamClass(request=request, session=session)
            if hasattr(p, 'update_precedence'):
                p.update_precedence()
            for k, v in current_step.get_parameter('form-values').items():
                p.param.set_param(k, v)
            form = generate_django_form(p, form_field_prefix='param-form-')()

            # Save changes to map view and layer groups
            context.update({
                # 'read_only': self.is_read_only(request, current_step), # TODO remove this from templates
                'form_title': form_title,
                'form': form,
            })

        # Bokeh Renderer
        elif renderer == 'bokeh':
            script = server_document(request.build_absolute_uri())
            context.update({
                # 'read_only': self.is_read_only(request, current_step), # TODO remove this from template
                'form_title': form_title,
                'script': script
            })

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
        """  # noqa: E501
        package, p_class = step.options['param_class'].rsplit('.', 1)
        mod = __import__(package, fromlist=[p_class])
        ParamClass = getattr(mod, p_class)
        if step.options['renderer'] == 'django':
            param_class_for_form = ParamClass(request=request, session=session)
            form = generate_django_form(param_class_for_form, form_field_prefix='param-form-')(request.POST)
            params = {}

            if not form.is_valid():
                raise RuntimeError('form is invalid')

            # Get the form from the post
            # loop through items and set the params
            for p in request.POST:
                if p.startswith('param-form-'):
                    try:
                        param_name = p[11:]
                        params[param_name] = form.cleaned_data[p]
                    except ValueError as e:
                        raise RuntimeError('error setting param data: {}'.format(e))

            # Get the param class and save the data from the form
            # for the next time the form is loaded
            param_class = ParamClass(request=request, session=session)
            param_values = dict(param_class.param.get_param_values())
            for k, v in params.items():
                try:
                    params[k] = type(param_values[k])(v)
                except ValueError as e:
                    raise ValueError('Invalid input to form: {}'.format(e))

            step.set_parameter('form-values', params)

        elif step.options['renderer'] == 'bokeh':
            # get document from the request here...
            params = {}

            for p in request.POST:
                if p.startswith('param-form-'):
                    try:
                        param_name = p[11:]
                        params[param_name] = request.POST.get(p, None)
                    except ValueError as e:
                        raise RuntimeError('error setting param data: {}'.format(e))

            param_class = ParamClass(request=request, session=session)
            param_values = dict(param_class.get_param_values())
            for k, v in params.items():
                try:
                    params[k] = type(param_values[k])(v)
                except ValueError as e:
                    raise ValueError('Invalid input to form: {}'.format(e))

            step.set_parameter('form-values', params)

        # Save parameters
        session.commit()

        # Validate the parameters
        step.validate()

        # Set the status
        step.set_status(status=step.STATUS_COMPLETE)
        session.commit()

        response = super().process_step_data(
            request=request,
            session=session,
            step=step,
            current_url=current_url,
            previous_url=previous_url,
            next_url=next_url
        )

        return response
