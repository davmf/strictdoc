package DoorDesign {
    part def Motor;

    part def Door {
        part motor : Motor;
        satisfy 'DOOR-REQ-1' by motor;
    }
}
