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
});