"""
This file serves as an extension to the DRF schema docs. It allows
to extract the schema and documenation from the endpoint's docstring
instead of being based only on django models.
"""

import re

import collections
import yaml
from rest_framework import schemas
from rest_framework.compat import coreapi, coreschema, uritemplate
from rest_framework.settings import api_settings
from django.utils.six.moves.urllib import parse as urlparse
import logging
logger = logging.getLogger(__name__)


class DocStringSchemaExtractor(schemas.AutoSchema):

    def get_link(self, path, method, base_url):
        description = self.get_description(path, method)

        description, param_description = self._split_description_from_parameter_details(description)
        fields = self.get_params_from_yaml(path, param_description)
        fields += self.get_serializer_fields(path, method)
        fields += self.get_pagination_fields(path, method)
        fields += self.get_filter_fields(path, method)

        manual_fields = self.get_manual_fields(path, method)
        fields = self.update_fields(fields, manual_fields)

        if fields and any([field.location in ('form', 'body') for field in fields]):
            encoding = self.get_encoding(path, method)
        else:
            encoding = None

        if base_url and path.startswith('/'):
            path = path[1:]

        return coreapi.Link(
            url=urlparse.urljoin(base_url, path),
            action=method.lower(),
            encoding=encoding,
            fields=fields,
            description=description
        )

    def _get_description_section(self, view, header, description):
        lines = [line for line in description.splitlines()]
        current_section = ''
        sections = {'': ''}
        coerce_method_names = api_settings.SCHEMA_COERCE_METHOD_NAMES
        sec_to_take = [header, coerce_method_names.get(header, None)]
        for line in lines:
            if schemas.inspectors.header_regex.match(line):
                potential_section, seperator, lead = line.partition(':')
                if potential_section in sec_to_take:
                    current_section = potential_section
                    sections[current_section] = lead.strip()
                else:
                    sections[current_section] += '\n' + line
            else:
                sections[current_section] += '\n' + line

        if header in sections:
            return sections[header].strip()
        if header in coerce_method_names:
            if coerce_method_names[header] in sections:
                return sections[coerce_method_names[header]].strip()
        return sections[''].strip()

    def _split_description_from_parameter_details(self, description):
        parts = description.split('---')
        if len(parts) == 1:
            return parts[0], ""
        elif len(parts) > 2:
            raise ValueError("Description contains more than one yaml seperator (---)")
        return parts

    def get_params_from_yaml(self, path, param_description):
        try:
            params = yaml.safe_load(param_description)
            if params is None:
                params = []
            elif 'parameters' in params:
                params = params['parameters']
        except yaml.YAMLError as e:
            logger.error('cannot parse yaml parameters for {}.{}: {}'.format(self.view, path, e))
            return []

        fields = []
        for param in params:
            desc = param.get('description', '')
            if 'example' in param:
                desc += " (Example: {})".format(param['example'])
            loc = param.get('location', 'path')
            typestring = param.get('type', 'string').title()
            if hasattr(coreschema, typestring):
                type_ = getattr(coreschema, typestring)
            else:
                type_ = coreschema.String
            field = coreapi.Field(
                name=param['name'],
                location=loc,
                required=param.get('required', loc == 'path'),
                schema=type_(title=param['name'], description=desc))
            fields.append(field)
        return fields

    def get_doc_fields(self, path, method, description):
        return self.get_params_from_yaml(path, description)
