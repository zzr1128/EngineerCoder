# -*- coding:utf-8 -*-

import json

from alias import *
from core.environment import Environment
from core.kit import Kit
from core.project import Project


@final
class ProjectArchive:
    class ArchiveError(Exception):
        pass

    @staticmethod
    def archive(project: Project, path: string) -> void:
        """
        Archive a project into a file at specified path.
        :raise ProjectArchive.ArchiveError: raise when serialization or file I/O fails
        """
        if not isinstance(project, Project):
            raise TypeError(f'Cannot archive {project} to {path}: invalid type')
        obj = serialize(project)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(obj, f, ensure_ascii=False, indent=4)
        except OSError:
            raise ProjectArchive.ArchiveError(f'Cannot archive {project} to {path}: I/O error')

    @staticmethod
    def unarchive(path: string, env: Environment) -> Project:
        """
        Load a project from a file at specified path.
        :raise ProjectArchive.ArchiveError: raise when deserialization or file I/O fails
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                obj = json.load(f)
        except OSError as exc:
            raise ProjectArchive.ArchiveError(f'Cannot unarchive {path}: I/O error ({exc})')
        proj: Project = deserialize(Project, obj)
        required_kits: IList[Kit] = []
        for kit_dict in proj.required_kits:
            required_kits.append(env.kit_manager[kit_dict['name']])
        proj.required_kits = required_kits
        return proj
