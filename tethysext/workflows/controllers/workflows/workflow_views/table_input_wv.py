"""
********************************************************************************
* Name: table_input_wv.py
* Author: EJones
* Created On: April 17, 2024
* Copyright: (c) Aquaveo 2024
********************************************************************************
"""
import inspect
import pandas as pd
import numpy as np
from pandas.api.types import is_numeric_dtype
from ..workflow_view import WorkflowView
from ....steps import TableInputStep
from ....utilities import strip_list


TABLE_DATASET_NODATA = -99999.9


class TableInputWV(WorkflowView):
    """
    Controller for a workflow view for entering a 2D dataset in an spreadsheet-like table.
    """
    template_name = 'workflows/workflows/table_input_wv.html'
    valid_step_classes = [TableInputStep]

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
        # Get previously saved dataset, if there is one
        dataset = current_step.get_parameter('dataset')
        max_rows = current_step.options.get('max_rows', current_step.DEFAULT_MAX_ROWS)

        # If not previously saved dataset, get the template dataset
        if dataset is None:
            dataset = current_step.options.get('template_dataset', current_step.DEFAULT_DATASET)

        if inspect.isfunction(dataset):
            dataset = dataset(request, session, current_step)

        # If the dataset is a dictionary (i.e.: previously saved dataset parameter), convert it to a DataFrame
        if isinstance(dataset, dict):
            dataset = pd.DataFrame.from_dict(dataset, orient='columns')

        # If the template dataset is empty (no rows),
        # generate rows to match the smaller of the initial row count and the max rows
        if dataset is None or (isinstance(dataset, pd.DataFrame) and dataset.empty):
            empty_rows = current_step.options.get('empty_rows', current_step.DEFAULT_EMPTY_ROWS)
            initial_rows = max_rows if empty_rows > max_rows else empty_rows
            dataset = pd.DataFrame(columns=dataset.columns, index=range(initial_rows), dtype=np.float64)

        # Reformat the data for rendering in the template
        rows = dataset.to_dict(orient='records')

        # Prepare columns dictionary
        column_is_numeric = {}
        for column in dataset.columns:
            is_numeric = is_numeric_dtype(dataset[column])
            column_is_numeric.update({column: is_numeric})

        context.update({
            'dataset_title': current_step.options.get('dataset_title', 'Dataset'),
            'columns': dataset.columns,
            'column_is_numeric': column_is_numeric,
            'rows': rows,
            'read_only_columns': current_step.options.get('read_only_columns', []),
            'plot_columns': current_step.options.get('plot_columns', []),
            'optional_columns': current_step.options.get('optional_columns', []),
            'max_rows': max_rows,
            'nodata_val': TABLE_DATASET_NODATA,
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

        Raises:
            ValueError: exceptions that occur due to user error, provide helpful message to help user solve issue.
            RuntimeError: exceptions that require developer attention.
        """  # noqa: E501
        # Post process the dataset
        data = {}
        template_dataset = step.options.get('template_dataset')
        if inspect.isfunction(template_dataset):
            template_dataset = template_dataset(request, session, step)
        columns = template_dataset.columns

        row_count = 0
        for column in columns:
            c = request.POST.getlist(column, [])
            strip_list(c)
            data.update({column: c})
            row_count = max(row_count, len(c))

        optional_columns = step.options.get('optional_columns', [])
        for column in columns:
            if column in optional_columns and not data[column]:
                c = [TABLE_DATASET_NODATA] * row_count
                data.update({column: c})

        # Save dataset as new pandas DataFrame
        dataset = pd.DataFrame(data=data, columns=columns)

        # Coerce columns to be the same types as the template dataset
        dataset = dataset.astype(template_dataset.dtypes, copy=True)

        # Reset the parameter to None for changes to be detected and saved.
        step.set_parameter('dataset', None)
        session.commit()

        # Save the new value of the dataset
        step.set_parameter('dataset', dataset.to_dict(orient='list'))
        session.commit()

        # Validate data if going to next step
        if 'next-submit' in request.POST:
            step.validate()

            # Update the status of the step
            step.set_status(step.ROOT_STATUS_KEY, step.STATUS_COMPLETE)
            step.set_attribute(step.ATTR_STATUS_MESSAGE, None)
            session.commit()

        return super().process_step_data(
            request=request,
            session=session,
            step=step,
            current_url=current_url,
            previous_url=previous_url,
            next_url=next_url
        )
