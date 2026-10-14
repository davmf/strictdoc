// Adds and deletes MEMBERS rows in the SysML element editor.
//
// A deleted row stays in the form with member_deleted=true, so that the
// server can remove the member from the file. Clicking the delete action
// again restores the row.

(() => {

  const SEL_ADD = '[data-js-sysml-add-member]';
  const SEL_DELETE = '[data-js-sysml-delete-member]';

  function addMemberRow(addAction) {
    const form = addAction.closest('form');
    const template = form.querySelector('template[data-js-sysml-new-member-row]');
    const members = form.querySelector('[data-js-sysml-members]');
    const row = template.content.firstElementChild.cloneNode(true);
    members.append(row);
    row.querySelector('input[type="text"]')?.focus();
  }

  function toggleMemberRow(deleteAction) {
    const row = deleteAction.closest('[data-js-sysml-member-row]');
    const deletedInput = row.querySelector('[data-js-sysml-member-deleted]');
    const isDeleted = deletedInput.value !== 'true';
    deletedInput.value = isDeleted ? 'true' : 'false';
    row.toggleAttribute('deleted', isDeleted);
    deleteAction.title = isDeleted ? 'Restore member' : 'Delete member';
  }

  document.addEventListener('click', (event) => {
    const addAction = event.target.closest?.(SEL_ADD);
    if (addAction) {
      event.preventDefault();
      addMemberRow(addAction);
      return;
    }
    const deleteAction = event.target.closest?.(SEL_DELETE);
    if (deleteAction) {
      event.preventDefault();
      toggleMemberRow(deleteAction);
    }
  });

})();
