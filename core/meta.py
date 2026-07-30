# -*- coding: utf-8 -*-

from alias import *
from dataclasses import dataclass


@final
@dataclass
class Version:
    major: int
    minor: int
    id: int

    __slots__ = ("major", "minor", "id")

    def __str__(self) -> string:
        return f"{self.major}.{self.minor} ({self.id})"

    def __lt__(self, other: Self) -> bool:
        return self.id < other.id

    def __le__(self, other: Self) -> bool:
        return self.id <= other.id

    def __gt__(self, other: Self) -> bool:
        return self.id > other.id

    def __ge__(self, other: Self) -> bool:
        return self.id >= other.id

    # pyrefly: ignore [bad-override]
    # noinspection method-overriding
    def __eq__(self, other: Self) -> bool:
        return self.id == other.id

    # pyrefly: ignore [bad-override]
    # noinspection method-overriding
    def __ne__(self, other: Self) -> bool:
        return self.id != other.id

    @staticmethod
    def satisfy(version: 'Version', lowest: Nullable['Version'], highest: Nullable['Version']):
        if lowest is not null and version < lowest:
            return False
        if highest is not null and version > highest:
            return False
        return True

    def __serialize__(self) -> IDictionary[string, int]:
        return {
            'major': self.major,
            'minor': self.minor,
            'id': self.id
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, int]) -> 'Version':
        require_member(data, 'major', 'minor', 'id')
        major = data['major']
        minor = data['minor']
        id_ = data['id']
        require_type(major, int)
        require_type(minor, int)
        require_type(id_, int)
        return Version(major, minor, id_)

    def __repr__(self) -> string:
        return f'Version<{self.major}.{self.minor} ({self.id})>'


@final
@dataclass
class SupportedLanguage:
    name: string
    id: string
    description: Nullable[string]

    # pyrefly: ignore [bad-override]
    # noinspection method-overriding
    def __eq__(self, other: Self) -> bool:
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __serialize__(self) -> IDictionary[string, Nullable[string]]:
        return {
            'name': self.name,
            'id': self.id,
            'description': self.description
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Nullable[string]]) -> Self:
        require_member(data, 'name', 'id', 'description')
        name = data['name']
        require_type(name, string)
        id_ = data['id']
        require_type(id_, string, 'id')
        description = data['description']
        name = NotNull(name)
        id_ = NotNull(id_)
        if description is not null:
            require_type(description, string)
        return cls(name, id_, description)

    def __repr__(self) -> string:
        return f'Language<name={self.name}, id={self.id}, description={self.description}>' \
              if self.description else \
              f'Language<name={self.name}, id={self.id}>'


@final
@dataclass
class AuthorInfo:
    name: string
    email: Nullable[string]
    remark: Nullable[string]

    def __serialize__(self) -> IDictionary[string, Nullable[string]]:
        return {
            'name': self.name,
            'email': self.email,
            'remark': self.remark
        }

    @classmethod
    def __deserialize__(cls, data: IDictionary[string, Nullable[string]]) -> Self:
        require_member(data, 'name', 'email', 'remark')
        assert data['name'] is not null, 'Author name cannot be null'
        name: string = NotNull(data['name'])
        require_type(name, string)
        email: Nullable[string] = data['email']
        if email is not null:
            require_type(email, string)
        remark: Nullable[string] = data['remark']
        if remark is not null:
            require_type(remark, string)
        return cls(name, email, remark)

    def __repr__(self) -> string:
        return f'Author<name={self.name}, email={self.email}, remark={self.remark}>' \
              if self.remark else \
              f'{self.name}, email={self.email}, remark={self.remark}>'
