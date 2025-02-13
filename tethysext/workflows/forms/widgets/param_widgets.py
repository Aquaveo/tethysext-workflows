"""
********************************************************************************
* Name: param_widgets.py
* Author: Scott Christensen and Nathan Swain
* Created On: January 18, 2019
* Copyright: (c) Aquaveo 2019
********************************************************************************
"""
import param
from django import forms
#from datetimewidget.widgets import DateWidget
from bootstrap_datepicker_plus.widgets import DatePickerInput
from django_select2.forms import Select2Widget, Select2MultipleWidget
from taggit.forms import TagField
# from dataframewidget.forms.fields import DataFrameField


widget_map = {
    param.Foldername:
        lambda po, p, name: forms.FilePathField(
            initial=po.param.inspect_value(name) or p.default,
            path=p.search_paths,
        ),
    param.Boolean:
        lambda po, p, name: forms.BooleanField(
            initial=po.param.inspect_value(name) or p.default, required=False
        ),
    # param.Array: ,
    # param.Dynamic: ,
    param.Filename:
        lambda po, p, name: forms.FileField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Dict:
        lambda po, p, name: forms.CharField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.XYCoordinates:
        lambda po, p, name: forms.MultiValueField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Selector:
        lambda po, p, name: forms.ChoiceField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    # param.HookList,
    # param.Action: ,
    param.parameterized.String:
        lambda po, p, name: forms.CharField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Magnitude:
        lambda po, p, name: forms.FloatField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    # param.Composite,
    param.Color:
        lambda po, p, name: forms.CharField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.ObjectSelector:
        lambda po, p, name: forms.ChoiceField(
            initial=po.param.inspect_value(name) or p.default,
            widget=Select2Widget,
            choices=p.get_range().items(),
        ),
    param.Number:
        lambda po, p, name: forms.FloatField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Range:
        lambda po, p, name: forms.MultiValueField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.NumericTuple:
        lambda po, p, name: forms.MultiValueField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Date:
        lambda po, p, name: forms.DateTimeField(
            initial=po.param.inspect_value(name) or p.default,
            widget=DatePickerInput(
                options={
                    'startDate': p.bounds[0].strftime(
                        '%Y-%m-%d') if p.bounds else '0000-01-01',  # start of supported time
                    'endDate': p.bounds[1].strftime(
                        '%Y-%m-%d') if p.bounds else '9999-12-31',  # end of supported time
                    'format': 'mm/dd/yyyy',
                    'autoclose': True,
                    # 'showMeridian': False,
                    'minView': 2,  # month view
                    'maxView': 4,  # 10-year overview
                    'todayBtn': True,
                    'clearBtn': True,
                    'todayHighlight': True,
                    'minuteStep': 5,
                    'pickerPosition': 'bottom-left',
                    'forceParse': 'true',
                    'keyboardNavigation': 'true',
                },
                bootstrap_version=3
            ),
        ),
    param.List:
        lambda po, p, name: TagField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Path:
        lambda po, p, name: forms.FilePathField(
            initial=po.param.inspect_value(name) or p.default,
            path=p.search_paths,
        ),
    param.MultiFileSelector:
        lambda po, p, name: forms.MultipleChoiceField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.ClassSelector:
        lambda po, p, name: forms.ChoiceField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.FileSelector:
        lambda po, p, name: forms.ChoiceField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.ListSelector:
        lambda po, p, name: forms.MultipleChoiceField(
            initial=po.param.inspect_value(name) or p.default,
            widget=Select2MultipleWidget,
            choices=p.get_range().items(),
        ),
    # param.Callable,
    param.Tuple:
        lambda po, p, name: forms.MultiValueField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    param.Integer:
        lambda po, p, name: forms.IntegerField(
            initial=po.param.inspect_value(name) or p.default,
        ),
    # TODO: Implement DataFrameField someday...
    # param.DataFrame:
    #     lambda po, p, name: DataFrameField(
    #         initial=po.param.inspect_value(name) is not None or p.default is not None
    #     )
}

widget_converter = {

}


def generate_django_form(parameterized_obj, form_field_prefix=None):
    """
    Create a Django form from a Parameterized object.

    Args:
        parameterized_obj(Parameterized): the parameterized object.
        form_field_prefix(str): A prefix to prepend to form fields
    Returns:
        Form: a Django form with fields matching the parameters of the given parameterized object.
    """
    # Create Django Form class dynamically
    class_name = '{}Form'.format(parameterized_obj.name.title())
    form_class = type(class_name, (forms.Form,), dict(forms.Form.__dict__))

    # Filter params based on precedence and constant state
    params = list(
        filter(
            lambda x: (x.precedence is None or x.precedence >= 0) and not x.constant,
            parameterized_obj.param.params().values()
        )
    )

    # Sort parameters based on precedence
    sorted_params = sorted(params, key=lambda p: p.precedence or 9999)

    for p in sorted_params:
        # TODO: Pass p.__dict__ as second argument instead of arbitrary
        p_name = p.name

        # Prefix parameter name if prefix provided
        if form_field_prefix is not None:
            p_name = form_field_prefix + p_name

        # Get appropriate Django field/widget based on param type
        form_class.base_fields[p_name] = widget_map[type(p)](parameterized_obj, p, p.name)

        # Set label with param label if set, otherwise derive from parameter name
        form_class.base_fields[p_name].label = p.name.replace("_", " ").title() if not p.label else p.label

        # Help text displayed on hover over field
        if p.doc:
            form_class.base_fields[p_name].widget.attrs.update({'title': p.doc})

        # Set required state from allow_None
        form_class.base_fields[p_name].required = p.allow_None

    return form_class
