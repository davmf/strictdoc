package 'PlantUML design' {
    part def Heater;

    part def Station {
        part heater : Heater;
        satisfy 'PUML-REQ-1' by heater;
    }
}
