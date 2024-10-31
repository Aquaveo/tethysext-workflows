import sys
import json
import logging
import traceback
from pprint import pprint
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import StatementError, ArgumentError
from sqlalchemy.orm.exc import NoResultFound
from django.http import JsonResponse
from django.utils.functional import wraps
from django.shortcuts import redirect
from django.contrib import messages
from ...exceptions import TethysWorkflowsException
from .helpers import set_step_status, parse_workflow_step_args
from ...utilities import clean_request, import_from_string
from ...models import Step
# DO NOT REMOVE, need to import all the subclasses of Step for the polymorphism to work.
from ...steps import *  # noqa: F401, F403
from ...results import *  # noqa: F401, F403
# END DO NOT REMOVE


log = logging.getLogger(f'tethys.{__name__}')

def workflow_controller(is_rest_controller=False):
    def decorator(controller_func):
        def _wrapped_controller(self, request, back_url=None, *args, **kwargs):
            session = None

            try:
                make_session = self.get_sessionmaker()
                session = make_session()

                # Call the Controller
                return controller_func(self, request, session, back_url, *args, **kwargs)

            except (StatementError, NoResultFound) as e:
                message = 'There was an error'
                log.exception(message)
                messages.warning(request, message)
                if not is_rest_controller:
                    return redirect(self.back_url)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            except TethysWorkflowsException as e:
                error_message = str(e)
                messages.warning(request, error_message)
                if not is_rest_controller:
                    return redirect(self.back_url)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            except ValueError as e:
                if session:
                    session.rollback()
                if not is_rest_controller:
                    return redirect(self.back_url)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            except RuntimeError as e:
                if session:
                    session.rollback()

                log.exception(str(e))
                messages.error(request, "We're sorry, an unexpected error has occurred.")
                if not is_rest_controller:
                    return redirect(self.back_url)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            finally:
                session and session.close()

        return wraps(controller_func)(_wrapped_controller)
    return decorator


def workflow_step_controller(is_rest_controller=False):
    def decorator(controller_func):
        def _wrapped_controller(self, request, workflow_id, step_id, back_url=None, session=None, *args, **kwargs):
            _Workflow = self.get_workflow_model()
            # Defer to outer scope if session is given
            manage_session = session is None
            current_step = None

            try:
                if manage_session:
                    make_session = self.get_sessionmaker()
                    session = make_session()


                workflow = self.get_workflow(request, workflow_id=workflow_id, session=session)
                current_step = self.get_step(request, step_id=step_id, session=session)

                # Call the Controller
                return controller_func(self, request, session, workflow, current_step, back_url,
                                       *args, **kwargs)

            except (StatementError, NoResultFound) as e:
                messages.warning(request, 'The {} could not be found.'.format(
                    _Workflow.DISPLAY_TYPE_SINGULAR.lower()
                ))
                if not is_rest_controller:
                    return redirect(self.back_url)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            except TethysWorkflowsException as e:
                error_message = str(e)
                messages.warning(request, error_message)
                if not is_rest_controller:
                    return redirect(self.back_url)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            except ValueError as e:
                if session:
                    session.rollback()
                    # Save error message to display to the user
                    if current_step:
                        current_step.set_attribute(current_step.ATTR_STATUS_MESSAGE, str(e))
                        current_step.set_status(current_step.ROOT_STATUS_KEY, current_step.STATUS_ERROR)
                        session.commit()

                if not is_rest_controller:
                    # Remove method so we redirect to the primary GET page...
                    c_request = clean_request(request)
                    return self.get(c_request, workflow_id=workflow_id, step_id=step_id)
                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            except RuntimeError as e:
                if session:
                    session.rollback()
                    # Save error message to display to the user
                    if current_step:
                        current_step.set_status(current_step.ROOT_STATUS_KEY, current_step.STATUS_ERROR)
                        session.commit()

                messages.error(request, "We're sorry, an unexpected error has occurred.")
                log.exception(e)
                if not is_rest_controller:
                    # Remove method so we redirect to the primary GET page...
                    c_request = clean_request(request)
                    return self.get(c_request, workflow_id=workflow_id, step_id=step_id)

                else:
                    return JsonResponse({'success': False, 'error': str(e)})

            finally:
                session and manage_session and session.close()

        return wraps(controller_func)(_wrapped_controller)
    return decorator


def workflow_step_job(job_func):
    def _wrapped():
        if job_func.__module__ == '__main__':
            args, unknown_args = parse_workflow_step_args()

            print('Given Arguments:')
            print(str(args))

            # Session vars
            step = None
            db_session = None
            ret_val = None

            try:
                # Get the database session 
                db_engine = create_engine(args.db_url)
                make_db_session = sessionmaker(bind=db_engine)
                db_session = make_db_session()

                # Import Workflow Class
                WorkflowClass = import_from_string(args.workflow_class)

                # Get the step
                # NOTE: if you get an error related to polymorphic_identity not being found, it may be caused by import
                # errors with a subclass of the Step. It could also be caused indirectly if the subclass
                # has Pickle typed columns with values that import things.
                step = db_session.query(Step).get(args.workflow_step_id)

                # Process parameters from workflow steps
                with open(args.workflow_params_file, 'r') as p:
                    params_json = json.loads(p.read())

                print('Workflow Parameters:')
                pprint(params_json)

                ret_val = job_func(
                    db_session=db_session,
                    workflow=step.workflow,
                    step=step,
                    gs_private_url=args.gs_private_url,
                    gs_public_url=args.gs_public_url,
                    workflow_class=WorkflowClass,
                    params_json=params_json,
                    params_file=args.workflow_params_file,
                    cmd_args=args,
                    extra_args=unknown_args
                )

                # Update step status
                print('Updating status...')
                set_step_status(db_session, step, step.STATUS_COMPLETE)

            except Exception as e:
                if step and db_session:
                    set_step_status(db_session, step, step.STATUS_FAILED)
                sys.stderr.write('Error processing {0}'.format(args.tethys_workflow_step_id))
                traceback.print_exc(file=sys.stderr)
                sys.stderr.write(repr(e))
                sys.stderr.write(str(e))

            finally:
                print('Closing session...')
                db_session and db_session.close()

            print('Processing Complete')
            return ret_val

    return _wrapped()
