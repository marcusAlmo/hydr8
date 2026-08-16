"""Django Forms for the Settings page POST endpoints.

Each form validates the submitted fields server-side.  The views call
the corresponding service after ``is_valid()`` passes.  Widget classes
match the Tailwind styling used in the existing templates so re-rendered
forms keep their look.
"""
from django import forms
from django.core.exceptions import ValidationError


# Shared input class — matches the templates' Tailwind input styling.
_INPUT_CLASS = (
    'w-full bg-surface-container-low border border-outline-variant/50 '
    'rounded-lg p-3 text-on-surface focus:ring-2 focus:ring-primary '
    'outline-none transition-all duration-200'
)
_MONO_INPUT_CLASS = (
    'w-full bg-surface-container-low border border-outline-variant/50 '
    'rounded-lg p-3 text-on-surface font-data-mono focus:ring-2 '
    'focus:ring-primary outline-none transition-all duration-200'
)


class CompanyForm(forms.Form):
    """Company tab — business identity fields."""
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': _INPUT_CLASS}),
    )
    contact_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': _MONO_INPUT_CLASS}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': _MONO_INPUT_CLASS}),
    )
    address = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': _INPUT_CLASS}),
    )


class ProfileForm(forms.Form):
    """My Profile tab — first/last name (self-service)."""
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': _INPUT_CLASS}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': _INPUT_CLASS}),
    )


class UsernameChangeForm(forms.Form):
    """Username change — requires current password verification."""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': _MONO_INPUT_CLASS,
            'autocomplete': 'current-password',
        }),
    )
    new_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': _MONO_INPUT_CLASS}),
    )


class PasswordChangeForm(forms.Form):
    """Self-service password change — requires current password.

    Distinct from ``apps.users.views.PasswordChangeForm`` (the forced
    post-temp-login form) which does NOT ask for the current password.
    """
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': _MONO_INPUT_CLASS,
            'autocomplete': 'current-password',
        }),
    )
    new_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': _MONO_INPUT_CLASS,
            'autocomplete': 'new-password',
        }),
    )
    confirm_password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': _MONO_INPUT_CLASS,
            'autocomplete': 'new-password',
        }),
    )

    def clean(self):
        cleaned = super().clean()
        new_pw = cleaned.get('new_password', '')
        confirm_pw = cleaned.get('confirm_password', '')
        if new_pw and confirm_pw and new_pw != confirm_pw:
            raise ValidationError("New passwords do not match.")
        return cleaned
