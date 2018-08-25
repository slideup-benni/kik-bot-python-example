$(document).ready(function () {
    if (kik.enabled) {
        kik.getUser(function (user) {
            if (user) {
                $("#message_from_user").val(user.username);
                alert(user.username);
            }
        });
    }
    $(document).on("click", ".user_link", function (event) {
        event.preventDefault();
        kik.showProfile($(event.target).data("user-id"));
        return false;
    });
    $(document).on("click", ".group_link", function (event) {
        event.preventDefault();
        kik.showProfile("#"+$(event.target).data("group-id"));
        return false;
    });

    $(document).on("keydown", "#message_body", function (event) {
        if ((event.keyCode === 10 || event.keyCode === 13) && event.ctrlKey) {
            $("#message_body").closest("form").submit()
        }
    });

    $(document).on("click", ".keyboard", function (event) {
        $('#message_body').val($(event.target).html());
        if (event.ctrlKey) {
            $("#message_body").closest("form").submit()
        }
    });
    $(document).on("submit", "form", function (event) {
        $(event.target).find("input[type=submit]").attr("disabled", "disabled");
        $(event.target).unbind('submit');
    });
    $('#message_body').select();
});