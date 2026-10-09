constructor_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("constructor_workspace"))
  
}

constructor_workspaceMod <- function(input, output, session, credentials, pool) {
  
  ns <- session$ns
  
  constructor_data <- reactiveValues(
    fleetsummary = NULL,
    preset = NULL,
    params = NULL,
    params_aircraft = NULL,
    alerts = NULL,
    alert_code = NULL,
    maintenance = NULL,
    config = NULL,
    preset_collection = NULL
  )
  
  output$constructor_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% tbl(in_schema("ecmapp", "_fleetsummary")) %>% collect()
    
    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- unique(fleetsummary$operator)[1]
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi
      
    }
    
    pickerInput(
      ns("constructor_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), #"utair", 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected, #"utair",
      multiple = F
    )
    
  })
  
  output$constructor_actype <- renderUI({
    
    ns <- session$ns
    # browser()
    choices <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        operator %in% !!input$constructor_operator_pi
      ) %>%
      group_by(
        operator,
        aircraft_type
      ) %>%
      summarise(
        count_ac = n_distinct(aircraft_id)
      ) %>%
      collect()
    
    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- choices$aircraft_type[1]
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_actype_pi
      
    }
    
    pickerInput(
      ns("constructor_actype_pi"),
      label = "A/C Type:", 
      choices = lapply(split(choices$aircraft_type, choices$operator), as.list),
      choicesOpt = list(
        subtext = unlist(lapply(split(choices$count_ac, choices$operator), as.list))
      ), 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,
      multiple = F
    )
    
  })
  
  output$constructor_acreg <- renderUI({
    
    ns <- session$ns
    
    # req(input$enginetrends_operator_pi, input$enginetrends_actype_pi)
    
    choices <- list()
    
    choicesOpt <- list()
    
    selected <- NULL
    # browser()
    if(!is.null(input$constructor_actype_pi) & !is.null(input$constructor_operator_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$constructor_operator_pi,
          aircraft_type %in% !!input$constructor_actype_pi,
          is.na(removal_datetime),
          !is.na(ac_reg_new),
          ac_reg_new != "-"
        ) %>%
        collect()
      
      fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
      
      fleetsummary <- fleetsummary %>% 
        group_by(
          aircraft_id, 
          engine_position
        ) %>%
        filter(
          install_datetime == max(install_datetime)
        )
      
      df_choices <- fleetsummary[,c(
        "aircraft_type",
        "ac_reg_new",
        "ac_reg_old",
        "aircraft_id",
        "engine_position",
        "engine_id"
      )] %>%
        group_by(
          aircraft_type,
          ac_reg_new,
          ac_reg_old,
          aircraft_id
        ) %>%
        tidyr::pivot_wider(
          names_from = engine_position,
          names_prefix = "esn_",
          values_from = c(
            engine_id
          )
        ) %>%
        mutate(
          subtext = paste0(
            ac_reg_old,
            " ",
            aircraft_id,
            ", pos.1: ",
            esn_1,
            ", pos.2: ",
            esn_2
          )
        )
      
      
      choices <- lapply(split(df_choices$ac_reg_new, df_choices$aircraft_type), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(df_choices$subtext, df_choices$aircraft_type), as.list))
      )
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(nrow(userdefault_test) == 0){
        
        selected <- choices$ac_reg_new[1]
        
      }
      
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_acreg_pi
        
      }
      
    }
    
    pickerInput(
      ns("constructor_acreg_pi"),
      label = "A/C Reg:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `dropdown-align-right` = TRUE
      ),
      selected = selected,
      multiple = T
    )
    
  })
  
  output$constructor_parameters_takeoff <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase == !!"TAKEOFF"
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_takeoff_pi"),
      label = "Parameters TAKEOFF",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
    
  })
  
  output$constructor_parameters_cruise <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase == !!"CRUISE"
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_cruise_pi"),
      label = "Parameters CRUISE",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
  })
  
  output$constructor_parameters_climb <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("CLIMB")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_climb_pi"),
      label = "Parameters CLIMB",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
    
  })
  
  output$constructor_parameters_eecm <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("EEC Maintenance")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_eecm_pi"),
      label = "Parameters EEC Maintenance",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
    
  })
  
  output$constructor_parameters_egpa <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("GasPath Advisory")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_egpa_pi"),
      label = "Parameters GasPath Advisory",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
  })
  
  output$constructor_parameters_start <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("START")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_start_pi"),
      label = "Parameters START",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
    
  })
  
  output$constructor_parameters_totdrt <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("TOTDRT")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_totdrt_pi"),
      label = "Parameters TOTDRT",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
    
  })
  
  output$constructor_parameters_toegt <- renderUI({
    
    ns <- session$ns
    # browser()
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("TOEGT")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_toegt_pi"),
      label = "Parameters TOEGT",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
    
  })
  
  output$constructor_parameters_oilcons <- renderUI({
    
    ns <- session$ns

    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$constructor_actype_pi,
        flight_phase %in% !!c("Oil consumption")
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters$parameter_sort <- 0
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_INPUT"] <- 1
    
    parameters$parameter_sort[parameters$table_name == "AIRCRAFT_RAW_OUTPT"] <- 2
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_INPUT"] <- 3
    
    parameters$parameter_sort[parameters$table_name == "ENGINE_RAW_OUTPUT"] <- 4
    
    parameters$parameter_sort[parameters$table_name == "flightinfo_input"] <- 5
    
    # parameters$table_name_flight_phase <- paste0(
    #   parameters$table_name,
    #   " (",
    #   parameters$flight_phase,
    #   ")"
    # )
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("constructor_parameters_oilcons_pi"),
      label = "Parameters Oil consumption",
      choices = choices,
      choicesOpt = choicesOpt,
      # selected = "TAKE OFF trends (MAIN)",
      options = list(
        `live-search`=TRUE
      ),
      multiple = T
    )
    
  })
  
  output$constructor_plotoptions <- renderUI({
    
    ns <- session$ns
    
    dropdownButton(
      
      inputId = "mydropdown_constructor",
      label = "Plot options",
      icon = icon("gear"),
      status = "default",
      circle = FALSE,
      tooltip = tooltipOptions(title = "Click to see options !"),
      accordion(
        id = "plotoptionsaccotdion_constructor",
        
        accordionItem(
          id = "accordion_item_0_constructor",
          title = "Position",
          status = "warning",
          collapsed = FALSE,
          
          radioButtons(
            ns("rb_engine_position"), 
            label = NULL,
            choices = list(
              "All" = 1,
              "Engine pos. 1" = 2,
              "Engine pos. 2" = 3
            ), 
            selected = 1
          )
        ),
        
        accordionItem(
          id = "accordion_item_1_constructor",
          title = "Smooth",
          status = "warning",
          collapsed = FALSE,
          
          radioButtons(
            ns("rb_enable_smooth"), 
            label = NULL,
            choices = list(
              "Only smooth" = 1,
              "Only raw" = 2,
              "Smooth and raw" = 3
            ), 
            selected = 3
          ),
          numericInput(
            ns("smooth_window"),
            label = NULL,
            15, 
            min = 1, 
            max = 100
          )
        ),
        accordionItem(
          id = "accordion_item_3_constructor",
          title = "Alerts/Maintenance",
          status = "warning",
          collapsed = FALSE,
          checkboxGroupInput(
            ns("cgi_show_alerts"),
            label = NULL,
            choices = c(
              "Show alerts",
              "Show maintenance actions",
              "Show previous installations"
            ),
            selected = c(
              "Show alerts",
              "Show previous installations"
            ),
            inline = FALSE
          )
        ),
        accordionItem(
          id = "accordion_item_4_constructor",
          title = "Graph size/range",
          status = "warning",
          collapsed = FALSE,
          radioGroupButtons(
            ns("rb_graph_size"),
            label = NULL,
            size = "sm",
            status = "warning",
            choices = c(
              `<i class='fa fa-th-large'></i>` = "multiple", 
              `<i class='fa fa-th-list'></i>` = "line", 
              `<i class='fa fa-stop'></i>` = "one"
            ),
            selected = "one",
            justified = FALSE
          ),
          radioButtons(
            ns("rb_range_selector"), 
            label = NULL,
            choices = list(
              "1m",
              "3m",
              "6m",
              "YTD",
              "1y",
              "ALL"
            ), 
            selected = "3m"
          )
        )
      )
    )
    
  })
  
  observeEvent(input$update_constructor_data, {
    # browser()
    
    if(
      any(
        is.null(input$constructor_operator_pi),
        is.null(input$constructor_actype_pi),
        is.null(input$constructor_acreg_pi),
        # is.null(headerselectors$constructor$constructor_presetname_pi()),
        is.null(input$rb_enable_smooth),
        is.null(input$smooth_window),
        is.null(input$cgi_show_alerts),
        is.null(input$rb_graph_size),
        is.null(input$rb_range_selector),
        is.null(input$rb_engine_position)
      ) & 
      all(
        is.null(input$constructor_parameters_cruise_pi),
        is.null(input$constructor_parameters_takeoff_pi),
        is.null(input$constructor_parameters_climb_pi),
        is.null(input$constructor_parameters_eecm_pi),
        is.null(input$constructor_parameters_egpa_pi),
        is.null(input$constructor_parameters_start_pi),
        is.null(input$constructor_parameters_todrt_pi),
        is.null(input$constructor_parameters_toegt_pi),
        is.null(input$constructor_parameters_oilcons_pi)
      )
    ){
      
      showModal(
        modalDialog(
          fluidPage(
            h3("Please select all elements of header")
          ),
          easyClose = TRUE
        )
      )
      
    }
    
    else{
      
      if(!is.null(input$rb_range_selector)){
        # browser()
        constructor_data$fleetsummary <- pool %>%
          tbl(in_schema("ecmapp", "_fleetsummary")) %>%
          filter(
            ac_reg_new %in% !!input$constructor_acreg_pi
          ) %>%
          collect()
        
        constructor_data$preset <- pool %>%
          tbl(in_schema("ecmapp", "parameters")) %>%
          filter(
            aircraft_type == !!input$constructor_actype_pi
          ) %>%
          collect()
        
        constructor_data$preset$parameter_name_flight_phase <- paste0(
          constructor_data$preset$parameter_name,
          " (",
          constructor_data$preset$flight_phase,
          ")"
        )
        
        constructor_data$preset$item_type <- substr(constructor_data$preset$engine_aircraft,1,1)
        
        # constructor_data$preset <- constructor_data$preset[
        #   constructor_data$preset$parameter_name_flight_phase %in% headerselectors$constructor$constructor_presetname_pi(),
        #   ]
        
        constructor_data$preset <- constructor_data$preset[
          constructor_data$preset$parameter_name_flight_phase %in% c(
            paste0(
              input$constructor_parameters_takeoff_pi,
              " (TAKEOFF)"
            ),
            paste0(
              input$constructor_parameters_cruise_pi,
              " (CRUISE)"
            ),
            paste0(
              input$constructor_parameters_climb_pi,
              " (CLIMB)"
            ),
            paste0(
              input$constructor_parameters_egpa_pi,
              " (GasPath Advisory)"
            ),
            paste0(
              input$constructor_parameters_eecm_pi,
              " (EEC Maintenance)"
            ),
            paste0(
              input$constructor_parameters_start_pi,
              " (START)"
            ),
            paste0(
              input$constructor_parameters_totdrt_pi,
              " (TOTDRT)"
            ),
            paste0(
              input$constructor_parameters_toegt_pi,
              " (TOEGT)"
            ),
            paste0(
              input$constructor_parameters_oilcons_pi,
              " (Oil consumption)"
            )
          ),
          ]
        
        #constructor_data$preset <- constructor_data$preset[constructor_data$preset$table_name != "flightinfo_input",]
        
        df_sort <- data.frame(
          parameter_name_flight_phase = input$rank_list_basic,
          id_sort = 1:length(input$rank_list_basic)
        )
        
        constructor_data$preset <- constructor_data$preset %>%
          left_join(
            df_sort,
            by = c(
              "parameter_name_flight_phase" = "parameter_name_flight_phase"
            )
          )
        
        colnames(constructor_data$preset)[
          colnames(constructor_data$preset) == "flight_phase"
          ] <- "main_flght_phs"
        
        colnames(constructor_data$preset)[
          colnames(constructor_data$preset) == "parameter_name"
          ] <- "main_param_name"
        
        constructor_data$params <- pool %>%
          tbl(in_schema("ecmapp", "engine_raw_output_mv")) %>%
          mutate(
            parameter_name_flight_phase = paste0(
              parameter_name,
              "_",
              flight_phase
            )
          ) %>%
          filter(
            aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
              parameter_name_flight_phase %in% !!unique(
                paste0(
                  constructor_data$preset$main_param_name,
                  "_",
                  constructor_data$preset$main_flght_phs
                )
              )
          ) %>%
          collect()
        browser()
        constructor_data$params <- rbind(
          constructor_data$params,
          pool %>%
            tbl(in_schema("ecmapp", "engine_input_mv")) %>%
            mutate(
              parameter_name_flight_phase = paste0(
                parameter_name,
                "_",
                flight_phase
              )
            ) %>%
            filter(
              aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
                parameter_name_flight_phase %in% !!unique(
                  paste0(
                    constructor_data$preset$main_param_name,
                    "_",
                    constructor_data$preset$main_flght_phs
                  )
                )
            ) %>%
            collect()
        )
        # browser()
        flightinfo_input <- pool %>%
          tbl(in_schema("ecmapp", "flightinfo_input_mv")) %>%
          mutate(
            parameter_name_flight_phase = paste0(
              parameter_name,
              "_",
              flight_phase
            )
          ) %>%
          filter(
            aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
              parameter_name_flight_phase %in% !!unique(
                paste0(
                  constructor_data$preset$main_param_name,
                  "_",
                  constructor_data$preset$main_flght_phs
                )
              )
          ) %>%
          collect()
        
        flightinfo_input$integer_value <- NA
        
        flightinfo_input$char_value <- NA
        
        constructor_data$params <- rbind(
          constructor_data$params,
          flightinfo_input
          
        )
        
        # constructor_data$params <- rbind(
        #   constructor_data$params,
        #   pool %>%
        #     tbl(in_schema("ecmapp", "flightinfo_input")) %>%
        #     mutate(
        #       parameter_name_flight_phase = paste0(
        #         parameter_name,
        #         "_",
        #         flight_phase
        #       )
        #     ) %>%
        #     filter(
        #       aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
        #         parameter_name_flight_phase %in% !!unique(
        #           paste0(
        #             constructor_data$preset$main_param_name,
        #             "_",
        #             constructor_data$preset$main_flght_phs
        #           )
        #         )
        #     ) %>%
        #     collect()
        # )
        
        aircraft <- pool %>%
          tbl(in_schema("ecmapp", "aircraft")) %>%
          filter(
            aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id)
          ) %>%
          collect()
        
        aircraft_names <- pool %>%
          tbl(in_schema("ecmapp", "aircraft_names")) %>%
          filter(
            ac_serial %in% !!unique(constructor_data$fleetsummary$aircraft_id)
          ) %>%
          collect()
        
        engine_config <- pool %>%
          tbl(in_schema("ecmapp", "engine_config")) %>%
          filter(
            engine_id %in% !!unique(constructor_data$fleetsummary$engine_id)
          ) %>%
          collect()
        
        constructor_data$params <- constructor_data$params %>%
          left_join(
            engine_config,
            by = c(
              "engine_id" = "engine_id"
            )
          )
        
        constructor_data$params <- constructor_data$params %>%
          left_join(
            aircraft_names,
            by = c(
              "aircraft_id" = "ac_serial"
            )
          )
        
        constructor_data$params <- constructor_data$params %>%
          left_join(
            aircraft,
            by = c(
              "aircraft_id" = "aircraft_id"
            )
          )
        
        # constructor_data$params_aircraft <- pool %>%
        #   tbl(in_schema("ecmapp", "aircraft_input")) %>%
        #   filter(
        #     aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
        #       flight_phase %in% !!constructor_data$preset$main_flght_phs &
        #       parameter_name %in% !!constructor_data$preset$main_param_name
        #   ) %>%
        #   collect()
        
        constructor_data$params_aircraft <- pool %>%
          tbl(in_schema("ecmapp", "aircraft_input_mv")) %>%
          mutate(
            parameter_name_flight_phase = paste0(
              parameter_name,
              "_",
              flight_phase
            )
          ) %>%
          filter(
            aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
              parameter_name_flight_phase %in% !!unique(
                paste0(
                  constructor_data$preset$main_param_name,
                  "_",
                  constructor_data$preset$main_flght_phs
                )
              )
          ) %>%
          collect()
        
        constructor_data$params_aircraft <- rbind(
          constructor_data$params_aircraft,
          pool %>%
            tbl(in_schema("ecmapp", "aircraft_raw_outpt_mv")) %>%
            mutate(
              parameter_name_flight_phase = paste0(
                parameter_name,
                "_",
                flight_phase
              )
            ) %>%
            filter(
              aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
                parameter_name_flight_phase %in% !!unique(
                  paste0(
                    constructor_data$preset$main_param_name,
                    "_",
                    constructor_data$preset$main_flght_phs
                  )
                )
            ) %>%
            collect()
        )
        
        constructor_data$params_aircraft <- constructor_data$params_aircraft %>%
          left_join(
            aircraft_names,
            by = c(
              "aircraft_id" = "ac_serial"
            )
          )
        
        constructor_data$params_aircraft <- constructor_data$params_aircraft %>%
          left_join(
            aircraft,
            by = c(
              "aircraft_id" = "aircraft_id"
            )
          )
        
        constructor_data$alerts <- pool %>%
          tbl(in_schema("ecmapp", "alert_output")) %>%
          filter(
            aircraft_id %in% !!unique(constructor_data$fleetsummary$aircraft_id) &
              flight_phase %in% !!constructor_data$preset$main_flght_phs &
              parameter_name %in% !!constructor_data$preset$main_param_name
          ) %>%
          collect()
        
        
        constructor_data$alert_code <- pool %>%
          tbl(in_schema("s7_mdb", "alert_code")) %>%
          collect()
        
        constructor_data$maintenance <- pool %>%
          tbl(in_schema("ecmapp", "maintenance")) %>%
          filter(
            engine_id %in% !!unique(constructor_data$fleetsummary$engine_id)
          ) %>%
          collect()
        
        constructor_data$maintenance <- constructor_data$maintenance[
          !duplicated(constructor_data$maintenance[,c("engine_id","maint_datetime")])
          ,]
        
        if(input$rb_range_selector == "1m"){
          
          constructor_data$range_selector <- 1
          
        }
        else if(input$rb_range_selector == "3m"){
          
          constructor_data$range_selector <- 2
          
        }
        else if(input$rb_range_selector == "6m"){
          
          constructor_data$range_selector <- 3
          
        }
        else if(input$rb_range_selector == "YTD"){
          
          constructor_data$range_selector <- 4
          
        }
        else if(input$rb_range_selector == "1y"){
          
          constructor_data$range_selector <- 5
          
        }
        else if(input$rb_range_selector == "ALL"){
          
          constructor_data$range_selector <- 6
          
        }
        
        if(input$rb_engine_position == "1"){
          
          rb_engine_position <- 0
          
        }
        else if(input$rb_engine_position == "2"){
          
          rb_engine_position <- 1
          
        }
        else if(input$rb_engine_position == "3"){
          
          rb_engine_position <- 2
          
        }
        
        if(rb_engine_position != 0){
          
          constructor_data$params <- constructor_data$params[constructor_data$params$engine_position == rb_engine_position,]
          
          constructor_data$alerts <- constructor_data$alerts[constructor_data$alerts$engine_position == rb_engine_position,]
          
          constructor_data$fleetsummary <- constructor_data$fleetsummary[constructor_data$fleetsummary$engine_position == rb_engine_position,]
          
        }
        
        if(!("Show previous installations" %in% input$cgi_show_alerts)){
          
          constructor_data$params <- constructor_data$params[
            !(constructor_data$params$engine_id %in% unique(
              constructor_data$fleetsummary$engine_id[!is.na(
                constructor_data$fleetsummary$removal_datetime
              )])),
            ]
          
          constructor_data$fleetsummary <- constructor_data$fleetsummary[is.na(
            constructor_data$fleetsummary$removal_datetime
          ),]
          
        }
        
        colors_smooth <- c("#007bff", "#17a2b8", "#28a745", "#ffc107", "#dc3545", "#f012be")
        
        colors_raw <- paste0(
          colors_smooth,
          "70"
        )
        
        status <- c("primary", "info", "success", "warning", "danger", "fuchsia")
        
        colors_smooth <- rep(colors_smooth, length.out = length(unique(constructor_data$fleetsummary$engine_id)))
        
        colors_raw <- rep(colors_raw, length.out = length(unique(constructor_data$fleetsummary$engine_id)))
        
        status <- rep(status, length.out = length(unique(constructor_data$fleetsummary$engine_id)))
        
        vec_engine_id <- stringr::str_sort(unique(constructor_data$fleetsummary$engine_id), decreasing = FALSE, numeric = TRUE)
        
        constructor_data$color_engine <- data.frame(
          colors_raw = colors_raw,
          colors_smooth = colors_smooth,
          engine_id = vec_engine_id,
          status = status,
          stringsAsFactors = FALSE
        )
        
        constructor_data$rb_enable_smooth = input$rb_enable_smooth
        constructor_data$cgi_show_alerts = input$cgi_show_alerts
        constructor_data$smooth_window = input$smooth_window
        constructor_data$rb_graph_size = input$rb_graph_size
        #constructor_data$rb_engine_position = headerselectors$plotoptions$rb_engine_position()
        browser()
      }
      
    }
    
    
    
  })
  
  output$constructor_preset <- renderUI({
    
    req(constructor_data$preset)
    
    if (is.null(constructor_data$preset)){
      return()
    }
    else{
      enginetrendsVisualization(
        fleetsummary = constructor_data$fleetsummary,
        preset = constructor_data$preset,
        params = constructor_data$params,
        paramssmooth = NULL,
        params_aircraft = constructor_data$params_aircraft,
        alerts = constructor_data$alerts,
        alert_code = constructor_data$alert_code,
        maintenance = constructor_data$maintenance,
        range_selector = constructor_data$range_selector,
        rb_enable_smooth = constructor_data$rb_enable_smooth,
        cgi_show_alerts = constructor_data$cgi_show_alerts,
        smooth_window = constructor_data$smooth_window,
        rb_graph_size = constructor_data$rb_graph_size,
        rb_engine_position = constructor_data$rb_engine_position,
        color_engine = constructor_data$color_engine
      )
    }
    
  })
  
  observeEvent(input$ab_export_constructor_preset, {
    screenshot(
      id = "constructor_preset",
      filename = "report_plot"
    )
  })
  
  observeEvent(input$ab_save_report,{
    showModal(modal_save_report)
  })
  # 
  # 
  modal_save_report <- modalDialog(
    fluidPage(
      h3("Please enter report credits"),
      textInput(
        ns("ti_report_name"),
        "Report name",
        value = "Enter report name ..."
      ),
      textAreaInput(
        ns("ti_report_description"),
        "Report description",
        value = "Enter report description ..."
      ),
      pickerInput(
        ns("pi_report_family"),
        "Report family",
        choices = c(
          "MAIN",
          "SPECIALIZED",
          "CUSTOM",
          "SAGE"
        ),
        selected = "MAIN"
      ),
      # useWaiter(), # dependencies
      #waiterShowOnLoad(spin_fading_circles()), # shows before anything else 
      #useWaiter(),
      checkboxInput(ns("visible"), "For all users", TRUE),
      actionBttn(ns("modal_ab_save_report"), "Save report")
    ),
    size="l"
  )
  
  # waiter_hide() # will hide *on_load waiter
  
  # w <- Waiter$new()
  # 
  observeEvent(input$modal_ab_save_report,{
    
    # preset <- pool %>%
    #   tbl(in_schema("ecmapp", "preset")) %>%
    #   select(
    #     report_name
    #   )  %>%
    #   collect()
    
    constructor_data$preset_collection <- pool %>%
      tbl(in_schema("ecmapp", "preset")) %>%
      collect()
    
    if(input$ti_report_name %in% unique(constructor_data$preset_collection$report_name)){
      
      showNotification(
        paste0(
          "Report with name",
          input$ti_report_name,
          " already exists. Please enter another name"
        )
        
      )
      
    }
    else{
      
      # w$show()
      # browser()
      # w$hide()
      
      parameters <- pool %>%
        tbl(in_schema("ecmapp", "parameters")) %>%
        filter(
          aircraft_type %in% !!unique(input$constructor_actype_pi)
        ) %>%
        collect()
      
      parameters$parameter_name_flight_phase <- paste0(
        parameters$parameter_name,
        " (",
        parameters$flight_phase,
        ")"
      )
      
      # parameters <- parameters[
      #   parameters$parameter_name_flight_phase %in% headerselectors$constructor$constructor_presetname_pi(),
      # ]
      
      labels_vec <- c(
        paste0(
          input$constructor_parameters_takeoff_pi,
          " (TAKEOFF)"
        ),
        paste0(
          input$constructor_parameters_cruise_pi,
          " (CRUISE)"
        ),
        paste0(
          input$constructor_parameters_climb_pi,
          " (CLIMB)"
        ),
        paste0(
          input$constructor_parameters_egpa_pi,
          " (GasPath Advisory)"
        ),
        paste0(
          input$constructor_parameters_eecm_pi,
          " (EEC Maintenance)"
        ),
        paste0(
          input$constructor_parameters_start_pi,
          " (START)"
        ),
        paste0(
          input$constructor_parameters_totdrt_pi,
          " (TOTDRT)"
        ),
        paste0(
          input$constructor_parameters_toegt_pi,
          " (TOEGT)"
        ),
        paste0(
          input$constructor_parameters_oilcons_pi,
          " (Oil consumption)"
        )
      )
      
      labels_vec <- labels_vec[
        !(labels_vec %in% 
        c(" (TAKEOFF)"," (CRUISE)"," (CLIMB)"," (GasPath Advisory)"," (EEC Maintenance)"," (START)"," (TOTDRT)"," (TOEGT)", " (Oil consumption)"))]
      
      parameters <- parameters[
        parameters$parameter_name_flight_phase %in% labels_vec,
        ]
      
      parameters <- data.frame(
        parameters %>% 
          left_join(
            data.frame(
              parameter_name_flight_phase = input$rank_list_basic,
              id_sort = 1:length(input$rank_list_basic)
            ),
            by = c(
              "parameter_name_flight_phase" = "parameter_name_flight_phase"
            )
          )
      )
      
      new_preset <- data.frame(
        
        report_name = rep(
          input$ti_report_name,
          nrow(parameters)
        ),
        main_param_name = parameters$parameter_name,
        main_flght_phs = parameters$flight_phase,
        table_name = parameters$table_name,
        item_type = substr(parameters$engine_aircraft,1,1),
        alias = rep(
          NA, 
          nrow(parameters)
        ),
        param_description = parameters$param_description,
        report_type = rep(
          input$pi_report_family,
          nrow(parameters)
        ),
        report_description = rep(
          input$ti_report_description,
          nrow(parameters)
        ),
        report_family = rep(
          input$pi_report_family,
          nrow(parameters)
        ),
        aircraft_family = parameters$aircraft_type,
        creation_date = rep(
          Sys.Date(),
          nrow(parameters)
        ),
        author = rep(
          credentials()$user,
          nrow(
            parameters
          )
        ),
        id_sort = parameters$id_sort,
        operator = rep(
          input$constructor_operator_pi,
          nrow(parameters)
        ),
        visible = rep(
          as.character(input$visible),
          nrow(
            parameters
          )
        )
      )
      
      dbWriteTable(pool, c("ecmapp", "preset"), value = new_preset, row.names = FALSE, append = TRUE)
      
      removeModal()
      
      showNotification(
        paste0(
          "Preset ",
          input$ti_report_name,
          " has been created"
        )
      )
      
    }
    
  })
  
  output$constructor_reporttable <- DT::renderDataTable({
    
    constructor_data$preset_collection <- pool %>%
      tbl(in_schema("ecmapp", "preset")) %>%
      filter(
        operator == !!input$constructor_operator_pi
      )  %>%
      group_by(
        report_name,
        report_description,
        report_family,
        aircraft_family,
        creation_date,
        author
      ) %>%
      summarise(
        number_of_params = n()
      ) %>%
      collect()
    
    DT::datatable({
      constructor_data$preset_collection
    },
    caption = "Report collection",
    extensions = 'Buttons',
    options = list(
      dom = 'Bfrtip',
      buttons = list(
        list(
          extend = 'collection',
          buttons = c('csv', 'excel'),
          exportOptions = list(
            modifiers = list(page = "all")
          )
        )
      ),
      columnDefs=list(list(className='dt-center',targets="_all")
      ),
      scrollX = TRUE
    ),
    filter = "top",
    selection = 'single',
    class = 'hover', 
    rownames = FALSE
    )
    
  })
  
  output$ui_delete_report <- renderUI({
    
    if(!is.null(input$constructor_reporttable_rows_selected)){
      
      actionBttn(ns("ab_delete_report"), "Delete report", color = "danger")
      
    }
    
  })
  
  observeEvent(input$ab_delete_report,{
    showModal(modal_delete_report)
  })
  
  
  modal_delete_report <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Do you really want to delete report"
        )
      ),
      # use_waiter(),
      actionBttn(ns("modal_ab_delete_report"), "Delete report", color = "danger")
    ),
    size="l"
  )
  
  observeEvent(input$modal_ab_delete_report,{
    # browser()
    report_name_to_delete <- unique(
      constructor_data$preset_collection$report_name[
        input$constructor_reporttable_rows_selected
        ]
    )
    
    constructor_data$preset_collection <- constructor_data$preset_collection[
      constructor_data$preset_collection$report_name != report_name_to_delete,
      ]
    
    preset <- pool %>%
      tbl(in_schema("ecmapp", "preset")) %>%
      collect()
    
    preset <- preset[preset$report_name != report_name_to_delete,]
    
    dbWriteTable(pool, c("ecmapp", "preset"), value = preset, row.names = FALSE, overwrite = TRUE)
    
    removeModal()
    
    showNotification(
      paste0(
        "Report ",
        report_name_to_delete,
        " has been deleted"
      )
    )
    
    # w$hide()
    
  })
  
  output$ui_constructor_id_sorted <- renderUI({
    
    labels_vec <- c(
      paste0(
        input$constructor_parameters_takeoff_pi,
        " (TAKEOFF)"
      ),
      paste0(
        input$constructor_parameters_cruise_pi,
        " (CRUISE)"
      ),
      paste0(
        input$constructor_parameters_climb_pi,
        " (CLIMB)"
      ),
      paste0(
        input$constructor_parameters_egpa_pi,
        " (GasPath Advisory)"
      ),
      paste0(
        input$constructor_parameters_eecm_pi,
        " (EEC Maintenance)"
      ),
      paste0(
        input$constructor_parameters_start_pi,
        " (START)"
      ),
      paste0(
        input$constructor_parameters_totdrt_pi,
        " (TOTDRT)"
      ),
      paste0(
        input$constructor_parameters_toegt_pi,
        " (TOEGT)"
      ),
      paste0(
        input$constructor_parameters_oilcons_pi,
        " (Oil consumption)"
      )
    )
    
    labels_vec <- labels_vec[
      !(labels_vec %in% 
      c(" (TAKEOFF)"," (CRUISE)"," (CLIMB)"," (GasPath Advisory)"," (EEC Maintenance)", " (START)", " (TOTDRT)", " (TOEGT)", " (Oil consumption)"))]
    
    labels <- as.list(
      labels_vec
    )
    
    
    # browser()
    rank_list_basic <- rank_list(
      text = "Drag the items in any desired order",
      labels = labels,
      input_id = ns("rank_list_basic")
    )
    
    rank_list_basic
    
    
  })
  
  output$constructor_report_table <- DT::renderDataTable(server = FALSE,{
    
    req(constructor_data$params)
    
    if (is.null(constructor_data$params)){
      return()
    }
    else{
      
      df <- constructor_data$params
      
      df_aircraft <- constructor_data$params_aircraft
      
      # df$float_value <- round(df$float_value,2)
      
      # df_aircraft$float_value <- round(df_aircraft$float_value,2)
      
      df <- df[,c(
        # "operator",
        "ac_reg_new",
        "aircraft_id",
        "aircraft_type",
        "engine_position",
        "engine_id",
        #"engine_type",
        "flight_phase",
        "flight_datetime",
        "parameter_name",
        "float_value"
      )] %>%
        group_by(
          # operator,
          ac_reg_new,
          aircraft_id,
          aircraft_type,
          engine_position,
          engine_id,
          #engine_type,
          flight_phase,
          flight_datetime,
          parameter_name
        ) %>%
        mutate(row = row_number()) %>%
        tidyr::pivot_wider(
          names_from = parameter_name,
          values_from = float_value
        ) %>%
        select(-row)
      
      df_aircraft <- df_aircraft[,c(
        # "operator",
        "ac_reg_new",
        "aircraft_id",
        "aircraft_type",
        #"engine_type",
        "flight_phase",
        "flight_datetime",
        "parameter_name",
        "float_value"
      )] %>%
        group_by(
          # operator,
          ac_reg_new,
          aircraft_id,
          aircraft_type,
          #engine_type,
          flight_phase,
          flight_datetime,
          parameter_name
        ) %>%
        mutate(row = row_number()) %>%
        tidyr::pivot_wider(
          names_from = parameter_name,
          values_from = float_value
        ) %>%
        select(-row)
      
      df_aircraft <- df_aircraft[!duplicated(df_aircraft),]
      
      df$flight_datetime <- as.character(df$flight_datetime)
      
      df_aircraft$flight_datetime <- as.character(df_aircraft$flight_datetime)
      
      df <- df %>%
        left_join(
          df_aircraft,
          by = c(
            "ac_reg_new" = "ac_reg_new",
            "aircraft_id" = "aircraft_id",
            "aircraft_type" = "aircraft_type",
            #"engine_type",
            "flight_phase" = "flight_phase",
            "flight_datetime" = "flight_datetime"
          )
        )
      
      if(nrow(df) == 0){
        
        df <- df_aircraft
        
      }
      
      DT::datatable({
        df
      },
      caption = "Report table",
      extensions = 'Buttons',
      options = list(
        dom = 'Bfrtip',
        buttons = list(
          list(
            extend = 'collection',
            buttons = c('csv', 'excel'),
            exportOptions = list(
              modifiers = list(page = "all")
            )
          )
        ),
        columnDefs=list(list(className='dt-center',targets="_all")
        ),
        scrollX = TRUE
      ),
      filter = "top",
      selection = 'single',
      class = 'hover', 
      rownames = FALSE
      )
      
    }
    
  })
  
  output$constructor_workspace <- renderUI({
    
    fluidRow(
      
      bs4Card(
        width = 12,
        headerBorder = FALSE,
        collapsible = FALSE,
        fluidRow(
          column(
            8,
            fluidRow(
              column(
                4,
                uiOutput(ns("constructor_operator"))
              ),
              column(
                4,
                uiOutput(ns("constructor_actype"))
              ),
              column(
                4,
                uiOutput(ns("constructor_acreg"))
              ),
              
              column(
                4,
                uiOutput(ns("constructor_parameters_takeoff"))
              ),
              column(
                4,
                uiOutput(ns("constructor_parameters_cruise"))
              ),
              column(
                4,
                hr(),
                dropdown(
                  style = "default", 
                  icon = icon("gear"), 
                  label = 'Other parameters',
                  uiOutput(ns("constructor_parameters_climb")),
                  uiOutput(ns("constructor_parameters_eecm")),
                  uiOutput(ns("constructor_parameters_egpa")),
                  uiOutput(ns("constructor_parameters_start")),
                  uiOutput(ns("constructor_parameters_totdrt")),
                  uiOutput(ns("constructor_parameters_toegt")),
                  uiOutput(ns("constructor_parameters_oilcons"))
                )
              )
            )
            
          ),
          br(),
          column(1),
          column(
            3,
            hr(),
            fluidRow(
              uiOutput(ns("constructor_plotoptions")),
              actionBttn(ns("update_constructor_data"), "Update plots")
            )
          )
        )
      ),
      
      bs4TabCard(
        width = 10,
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Report plot",
          # br(),
          dropdown(
            # tags$h3("List of Input"),
            actionBttn(ns("ab_export_constructor_preset"), "Download image"),
            hr(),
            actionBttn(ns("ab_save_report"), "Save preset")
          ),
          br(),
          #withSpinner(uiOutput(ns("constructor_preset")))
          div(
            style = 'overflow-y:scroll;height:800px;',
            withSpinner(uiOutput(ns("constructor_preset")))
          )
        ),
        tabPanel(
          title = "Report table",
          # withSpinner(DT::dataTableOutput(ns("constructor_reporttable")))
          withSpinner(DT::dataTableOutput(ns("constructor_report_table")))
        ),
        tabPanel(
          title = "Report collection",
          # withSpinner(DT::dataTableOutput(ns("constructor_reporttable")))
          withSpinner(DT::dataTableOutput(ns("constructor_reporttable"))),
          uiOutput(ns("ui_delete_report"))
        )
      ),
      bs4Card(
        width = 2,
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        uiOutput(ns("ui_constructor_id_sorted"))
      )
    )
    
    
  })
  
  return(reactive({constructor_data}))
  
}