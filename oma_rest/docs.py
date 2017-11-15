
'''
This file serves as an extension to the DRF docs. It removes the model dependancy when accesing parameter descriptions.

'''


import re

import collections
from rest_framework import  schemas
from rest_framework.utils import formatting
from rest_framework.compat import coreapi, coreschema, uritemplate
from django.utils.encoding import smart_text
from django.utils.html import urlize
import logging
logger = logging.getLogger(__name__)


header_regex = re.compile('^[a-zA-Z][0-9A-Za-z_]*:')


class ModifiedSchemaGenerator(schemas.SchemaGenerator):

    def get_description(self, path, method, view):
        method_name = getattr(view, 'action', method.lower())
        method_docstring = getattr(view, method_name, None).__doc__
        if method_docstring:
            # An explicit docstring on the method or action.
            try:
                method_docstring = re.split(r':(?:query)?param', method_docstring, 1)[0]
            except:
                pass
            return urlize(formatting.dedent(smart_text(method_docstring)))

        description = view.get_view_description()
        lines = [line.strip() for line in description.splitlines()]
        current_section = ''
        sections = {'': ''}

        for line in lines:
            if header_regex.match(line):
                current_section, seperator, lead = line.partition(':')
                sections[current_section] = lead.strip()
            else:
                sections[current_section] += '\n' + line

        header = getattr(view, 'action', method.lower())
        if header in sections:
            return sections[header].strip()
        if header in self.coerce_method_names:
            if self.coerce_method_names[header] in sections:
                return sections[self.coerce_method_names[header]].strip()
        return sections[''].strip()

    def get_path_fields(self, path, method, view):
        method_name = getattr(view, 'action', method.lower())
        method_docstring = getattr(view, method_name, None).__doc__

        # split docstring in "general part" - "params" - "queryparams"
        params = collections.defaultdict(list)
        cur_pos = 0
        cur_typ = 'general'
        for mo in re.finditer(r':(?P<typ>(?:query)?param)', method_docstring):
            params[cur_typ].append(method_docstring[cur_pos:mo.start()])
            cur_pos = mo.end()+1
            cur_typ = mo.group('typ')
        params[cur_typ].append(method_docstring[cur_pos:])

        fields = []

        for variable in uritemplate.variables(path):
            title = ''
            description = ''
            if 'param' in params:
                for param_doc in params['param']:
                    if variable in param_doc:
                        try:
                            desc_part = param_doc.split(":", 1)[1]
                        except KeyError:
                            desc_part = param_doc.split(variable)[1]
                        description = formatting.dedent(smart_text(desc_part))
                        break
            schema_cls = coreschema.String

            field = coreapi.Field(
                name=variable,
                location='path',
                required=True,
                schema=schema_cls(title=title, description=description))
            fields.append(field)

        if 'queryparam' in params:
            schema_cls = coreschema.String
            for qparam_doc in params['queryparam']:
                try:
                    qname, desc = qparam_doc.split(':', 1)
                except ValueError:
                    logger.error('cannot determine queryparam name/desc from "{}"'
                                 .format(qparam_doc))
                    continue
                field = coreapi.Field(
                    name=qname.strip(),
                    location='query',
                    required=False,
                    schema=schema_cls(title='', description=desc))
                fields.append(field)

        return fields
