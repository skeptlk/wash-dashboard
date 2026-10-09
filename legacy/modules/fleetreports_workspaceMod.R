fleetreports_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("fleetreports_workspace"))
  
}

fleetreports_workspaceMod <- function(input, output, session, credentials, pool) {
  
  ns <- session$ns
  
  output$fleetreport_operator <- renderUI({
    
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
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_operator_pi
      
    }
    
    pickerInput(
      ns("fleetreports_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator),  #"utair",
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected =  selected, # "utair",
      multiple = F
    )
    
  })
  
  output$fleetreport_actype <- renderUI({
    
    ns <- session$ns
    # 
    
    if(!is.null(input$fleetreports_operator_pi)){
      
      choices <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$fleetreports_operator_pi,
          !is.na(ac_reg_new),
          ac_reg_new != "-"
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
      
      if(
        nrow(userdefault_test) == 0 |
        jsonlite::fromJSON(userdefault_test$default)$fleetreports_operator_pi != input$fleetreports_operator_pi
      ){
        
        selected <- choices$aircraft_type[1]
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_actype_pi
        
      }
      
      #choices <- choices[!(choices$aircraft_type %in% c("ERJ175", "A330-200","B777-300ER")),]
      
      pickerInput(
        ns("fleetreports_actype_pi"),
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
        selected = selected,#"ATR72-212",
        multiple = T
      )
      
    }
    
    
  })
  
  output$fleetreport_acreg <- renderUI({
    
    ns <- session$ns
    
    #req(input$fleetreports_actype_pi, input$fleetreports_operator_pi)
    
    choices <- list()
    
    choicesOpt <- NULL
    
    selected <- NULL
    
    if(!is.null(input$fleetreports_actype_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$fleetreports_operator_pi,
          aircraft_type %in% !!input$fleetreports_actype_pi,
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
      
      if(
        nrow(userdefault_test) == 0 |
        jsonlite::fromJSON(userdefault_test$default)$fleetreports_operator_pi != input$fleetreports_operator_pi
      ){
        
        selected <- df_choices$ac_reg_new
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_acreg_pi
        
      }
    }
    pickerInput(
      ns("fleetreports_acreg_pi"),
      label = "A/C Reg:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = selected,
      multiple = T
    )
    
  })
  
  output$fleetreport_presetname <- renderUI({
    
    ns <- session$ns
    
    choices_list <- NULL
    
    choices_opt_list <- NULL
    
    selected <- NULL
    
    #req(input$enginetrends_actype_pi, input$enginetrends_operator_pi)
    if(!is.null(input$fleetreports_operator_pi)){
      preset <- pool %>%
        tbl(in_schema("ecmapp", "preset")) %>%
        filter(
          aircraft_family %in% c(
            !!input$fleetreports_actype_pi,
            "ALL"
          ) &
            operator %in% !!input$fleetreports_operator_pi # OPERATOR IN SELECTED PRESET NAME !!!!!!!!!!!!!!!!!!!!!
        ) %>%
        group_by(
          report_name,
          report_family
        ) %>%
        summarise(
          count_params = n_distinct(main_param_name)
        ) %>%
        mutate(
          subtext = paste(count_params, "params")
        ) %>%
        collect()
      
      # choices_list <- list()
      # 
      # choices_opt_list <- list()
      # 
      # for(report_family in unique(preset$report_family)){
      #   
      #   choices_list[[report_family]] <- preset$report_name[preset$report_family == report_family]
      #   
      #   choices_opt_list[[report_family]] <- paste0(
      #     preset$count_params[preset$report_family == report_family],
      #     " params"
      #   )
      #   
      # }
      
      choices <- lapply(split(preset$report_name, preset$report_family), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(preset$subtext, preset$report_family), as.list))
      )
      
      choices <- choices[order(match(names(choices), c("MAIN","SPECIALIZED", "CUSTOM")))]
      
      choicesOpt <- choicesOpt[order(match(names(choicesOpt), c("MAIN","SPECIALIZED", "CUSTOM")))]
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(
        nrow(userdefault_test) == 0 |
        jsonlite::fromJSON(userdefault_test$default)$fleetreports_operator_pi != input$fleetreports_operator_pi
      ){
        
        # selected <- c("TAKE OFF trends (MAIN)")
        
        selected <- preset$report_name[1]
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$fleetreports_presetname_pi
        
      }
      
      pickerInput(
        ns("fleetreports_presetname_pi"),
        label = "Preset",
        choices = choices, 
        choicesOpt = choicesOpt,
        selected = selected,
        options = list(
          `live-search`=TRUE
        ),
        multiple = F
      )
    }
    
  })
  
  output$fleetreport_plotoptions <- renderUI({
    
    ns <- session$ns
    
    dropdownButton(
      label = "Report options",
      # circle = TRUE,
      # status = "danger",
      # icon = icon("gear"), 
      # width = "300px",
      # tooltip = tooltipOptions(title = "Click to see options !"),
      icon = icon("gear"),
      status = "default",
      circle = FALSE,
      tooltip = tooltipOptions(title = "Click to see options !"),
      hr(),
      hr(),
      hr(),
      hr(),
      hr(),
      checkboxInput(
        ns("ci_date_point"),
        "Selection by date",
        value = TRUE, 
        width = NULL
      ),
      uiOutput(ns("ui_date_point")),
      hr(),
      radioButtons(
        ns("rb_enable_smooth"), 
        label = NULL,
        choices = list(
          "Only smooth" = 1,
          "Only raw" = 2,
          "Smooth and raw" = 3
        ), 
        #selected = 3
        selected = 3
      ),
      numericInput(
        ns("smooth_window"),
        label = NULL,
        15, 
        min = 1, 
        max = 100
      )
    )
    
  })
  
  output$ui_date_point <- renderUI({
    
    if(input$ci_date_point){
      
      column(
        12,
        dateInput(
          ns("fleetreports_datestart_di"), 
          "Start Date", 
          value = Sys.Date()-30,
          width = '200px'
        ),
        dateInput(
          ns("fleetreports_dateend_di"), 
          "End Date", 
          value = Sys.Date(),
          width = '200px'
        )
      )
      
    }
    else{
      numericInput(
        ns("fleetreports_numpoint_ni"),
        "Number of points",
        5,
        min = 2,
        max = 100
      ) 
    }
  })
  
  fleetreports_data <- reactiveValues(
    fleetsummary = NULL,
    preset = NULL,
    params = NULL,
    params_aircraft = NULL,
    alerts = NULL,
    alert_code = NULL,
    maintenance = NULL,
    config = NULL
  )
  
  observeEvent(input$update_fleetreport_data, {
    
    fleetreports_data$fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "_fleetsummary")) %>%
      filter(
        ac_reg_new %in% !!input$fleetreports_acreg_pi
      ) %>% 
      collect()
    
    fleetreports_data$preset <- pool %>%
      tbl(in_schema("ecmapp", "preset")) %>%
      filter(
        report_name == !!input$fleetreports_presetname_pi & 
          operator %in% !!input$fleetreports_operator_pi & 
          !is.na(report_name) & 
          !is.na(main_param_name) & 
          !is.na(main_flght_phs)
      ) %>%
      group_by(
        report_name,
        main_param_name,
        main_flght_phs,
        table_name,
        alias,
        param_description,
        item_type,
        id_sort
      ) %>%
      summarise(
        count_params = n()
      ) %>%
      collect()
    
    if(input$ci_date_point){
      
      if(is.null(input$fleetreports_datestart_di)&is.null(input$fleetreports_datestart_di)){
        
        fleetreports_datestart_di <- Sys.Date()-30
        fleetreports_dateend_di <- Sys.Date()
        
      }
      else{
        fleetreports_datestart_di <- input$fleetreports_datestart_di
        fleetreports_dateend_di <- input$fleetreports_dateend_di
      }
      
      
    }
    else{
      
      fleetreports_datestart_di <- Sys.Date() - 365
      fleetreports_dateend_di <- Sys.Date()
      
    }
    
    fleetreports_data$params <- pool %>%
      tbl(in_schema("ecmapp", "engine_raw_output_mv")) %>%
      mutate(
        parameter_name_flight_phase = paste0(
          parameter_name,
          "_",
          flight_phase
        )
      ) %>%
      filter(
        aircraft_id %in% !!unique(fleetreports_data$fleetsummary$aircraft_id) &
          parameter_name_flight_phase %in% !!unique(
            paste0(
              fleetreports_data$preset$main_param_name,
              "_",
              fleetreports_data$preset$main_flght_phs
            )
          ) &
          # as.Date(flight_datetime) >= !!input$fleetreports_datestart_di & 
          # as.Date(flight_datetime) <= !!input$fleetreports_dateend_di
          as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
          as.Date(flight_datetime) <= !!fleetreports_dateend_di
      ) %>%
      collect()
    
    fleetreports_data$params <- rbind(
      fleetreports_data$params,
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
          aircraft_id %in% !!unique(fleetreports_data$fleetsummary$aircraft_id) &
            parameter_name_flight_phase %in% !!unique(
              paste0(
                fleetreports_data$preset$main_param_name,
                "_",
                fleetreports_data$preset$main_flght_phs
              )
            ) &
            # as.Date(flight_datetime) >= !!input$fleetreports_datestart_di & 
            # as.Date(flight_datetime) <= !!input$fleetreports_dateend_di
            as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
            as.Date(flight_datetime) <= !!fleetreports_dateend_di
        ) %>%
        collect()
    )
    
    fleetreports_data$params_aircraft <- pool %>%
      tbl(in_schema("ecmapp", "aircraft_input_mv")) %>%
      mutate(
        parameter_name_flight_phase = paste0(
          parameter_name,
          "_",
          flight_phase
        )
      ) %>%
      filter(
        aircraft_id %in% !!unique(fleetreports_data$fleetsummary$aircraft_id) &
          parameter_name_flight_phase %in% !!unique(
            paste0(
              fleetreports_data$preset$main_param_name,
              "_",
              fleetreports_data$preset$main_flght_phs
            )
          ) &
          # as.Date(flight_datetime) >= !!input$fleetreports_datestart_di & 
          # as.Date(flight_datetime) <= !!input$fleetreports_dateend_di
          as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
          as.Date(flight_datetime) <= !!fleetreports_dateend_di
      ) %>%
      collect()
    
    fleetreports_data$params_aircraft <- rbind(
      fleetreports_data$params_aircraft,
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
          aircraft_id %in% !!unique(fleetreports_data$fleetsummary$aircraft_id) &
            parameter_name_flight_phase %in% !!unique(
              paste0(
                fleetreports_data$preset$main_param_name,
                "_",
                fleetreports_data$preset$main_flght_phs
              )
            ) &
            # as.Date(flight_datetime) >= !!input$fleetreports_datestart_di & 
            # as.Date(flight_datetime) <= !!input$fleetreports_dateend_di
            as.Date(flight_datetime) >= !!fleetreports_datestart_di & 
            as.Date(flight_datetime) <= !!fleetreports_dateend_di
        ) %>%
        collect()
    )
    
    browser()
    
    if(nrow(fleetreports_data$params) > 0){
      
      fleetreports_data$params <- fleetreports_data$params %>%
        arrange(
          aircraft_id,
          engine_position,
          engine_id,
          flight_phase,
          parameter_name,
          flight_datetime
        ) %>% 
        group_by(
          aircraft_id,
          engine_position,
          engine_id,
          flight_phase,
          parameter_name
        ) %>%
        mutate(
          # float_value_smooth_1 = rollapply(
          #   float_value,
          #   input$smooth_window,
          #   mean,
          #   align = 'right',
          #   fill = NA
          # ),
          float_value_smooth = caTools::runmean(
            x = float_value,
            k = input$smooth_window,
            align = "right"
          )
        )   
    }
   
    
    #flight_datetime <- sort(unique(fleetreports_data$params$flight_datetime), decreasing = TRUE)
    
    if(!input$ci_date_point){
      
      fleetreports_data$params <- fleetreports_data$params[
        with(fleetreports_data$params, order(engine_id, flight_datetime)),
        ]
      
      fleetreports_data$params_aircraft <- fleetreports_data$params_aircraft[
        with(fleetreports_data$params_aircraft, order(aircraft_id, flight_datetime)),
        ]
      
      fleetreports_data$params <- fleetreports_data$params %>% 
        group_by(aircraft_id, engine_position, flight_phase, engine_id, parameter_name) %>% 
        slice(tail(row_number(), input$fleetreports_numpoint_ni))
      
      fleetreports_data$params_aircraft <- fleetreports_data$params_aircraft %>% 
        group_by(aircraft_id, flight_phase, parameter_name) %>% 
        slice(tail(row_number(), input$fleetreports_numpoint_ni))
      
    }
    # fleetreports_data$params <- fleetreports_data$params[fleetreports_data$params$flight_datetime %in% flight_datetime,]
    # fleetreports_data$params_aircraft <- fleetreports_data$params_aircraft[fleetreports_data$params_aircraft$flight_datetime %in% flight_datetime,]
    
    fleetreports_data$params$float_value[
      !is.na(fleetreports_data$params$integer_value)
      ] <- fleetreports_data$params$integer_value[
        !is.na(fleetreports_data$params$integer_value)
        ]
    
    fleetreports_data$params_aircraft$float_value[
      !is.na(fleetreports_data$params_aircraft$integer_value)
      ] <- fleetreports_data$params_aircraft$integer_value[
        !is.na(fleetreports_data$params_aircraft$integer_value)
        ]
    
    aircraft <- pool %>%
      tbl(in_schema("ecmapp", "aircraft")) %>%
      filter(
        aircraft_id %in% !!unique(fleetreports_data$fleetsummary$aircraft_id)
      ) %>%
      collect()
    
    aircraft_names <- pool %>%
      tbl(in_schema("ecmapp", "aircraft_names")) %>%
      filter(
        ac_serial %in% !!unique(fleetreports_data$fleetsummary$aircraft_id)
      ) %>%
      collect()
    
    engine_config <- pool %>%
      tbl(in_schema("ecmapp", "engine_config")) %>%
      filter(
        engine_id %in% !!unique(fleetreports_data$fleetsummary$engine_id)
      ) %>%
      collect()
    
    fleetreports_data$params <- fleetreports_data$params %>%
      left_join(
        engine_config,
        by = c(
          "engine_id" = "engine_id"
        )
      )
    
    fleetreports_data$params <- fleetreports_data$params %>%
      left_join(
        aircraft_names,
        by = c(
          "aircraft_id" = "ac_serial"
        )
      )
    
    fleetreports_data$params <- fleetreports_data$params %>%
      left_join(
        aircraft,
        by = c(
          "aircraft_id" = "aircraft_id"
        )
      )
    
    fleetreports_data$params_aircraft <- fleetreports_data$params_aircraft %>%
      left_join(
        aircraft_names,
        by = c(
          "aircraft_id" = "ac_serial"
        )
      )
    
    fleetreports_data$params_aircraft <- fleetreports_data$params_aircraft %>%
      left_join(
        aircraft,
        by = c(
          "aircraft_id" = "aircraft_id"
        )
      )
    
  })
  
  output$fleetreports_table <- renderReactable({
    
    req(fleetreports_data$params)
    
    if (is.null(fleetreports_data$params)){
      return()
    }
    else{
      browser()
      params <- fleetreports_data$params[with(fleetreports_data$params, order(engine_id, flight_datetime)),]
      
      params_nest_1 <- params[
        params$parameter_name_flight_phase == unique(params$parameter_name_flight_phase)[1],
        c(
          "ac_reg_new","engine_position","engine_id",
          "parameter_name_flight_phase","flight_datetime", 
          "float_value" #, "integer_value", "char_value"
        )] %>% 
        tidyr::nest(-c(ac_reg_new,engine_position, engine_id))
      
      colnames(params_nest_1)[
        colnames(params_nest_1) == "data"
        ] <- unique(params$parameter_name_flight_phase)[1]
      
      params_nest_1_smooth <- params[
        params$parameter_name_flight_phase == unique(params$parameter_name_flight_phase)[1],
        c(
          "ac_reg_new","engine_position","engine_id",
          "parameter_name_flight_phase","flight_datetime", 
          "float_value_smooth" #, "integer_value", "char_value"
        )] %>% 
        tidyr::nest(-c(ac_reg_new,engine_position, engine_id))
      
      colnames(params_nest_1_smooth)[
        colnames(params_nest_1_smooth) == "data"
        ] <- paste0(unique(params$parameter_name_flight_phase)[1],"_smooth")
      
      params_nest_1 <- params_nest_1 %>%
        left_join(
          params_nest_1_smooth,
          by = c(
            "ac_reg_new" = "ac_reg_new",
            "engine_position" = "engine_position",
            "engine_id" = "engine_id"
          )
        )
      
      if(length(unique(params$parameter_name_flight_phase)) > 1){
        for(
          parameter_name_flight_phase in unique(params$parameter_name_flight_phase)[
            2:length(unique(params$parameter_name_flight_phase))
            ]
        ){
          
          params_nest_n <- params[
            params$parameter_name_flight_phase == parameter_name_flight_phase,
            ] %>% 
            nest(-c(ac_reg_new,engine_position, engine_id))  
          
          colnames(params_nest_n)[
            colnames(params_nest_n) == "data"
            ] <- parameter_name_flight_phase
          
          params_nest_n_smooth <- params[
            params$parameter_name_flight_phase == parameter_name_flight_phase,
            c(
              "ac_reg_new","engine_position","engine_id",
              "parameter_name_flight_phase","flight_datetime", 
              "float_value_smooth" #, "integer_value", "char_value"
            )] %>% 
            tidyr::nest(-c(ac_reg_new,engine_position, engine_id))
          
          colnames(params_nest_n_smooth)[
            colnames(params_nest_n_smooth) == "data"
            ] <- paste0(parameter_name_flight_phase,"_smooth")
          
          params_nest_1 <- params_nest_1 %>%
            left_join(
              params_nest_n,
              by = c(
                "ac_reg_new" = "ac_reg_new",
                "engine_position" = "engine_position",
                "engine_id" = "engine_id"
              )
            ) %>%
            left_join(
              params_nest_n_smooth,
              by = c(
                "ac_reg_new" = "ac_reg_new",
                "engine_position" = "engine_position",
                "engine_id" = "engine_id"
              )
            )
          
        }
      }
      
      create_plot <- function(x){
        
        x$flight_datetime <- datetime_to_timestamp(x$flight_datetime)
        
        if(is.null(x$float_value)){
          
          x$float_value <- x$float_value_smooth
        }
        
        hchart(x, "area", hcaes(x = flight_datetime, y = float_value)) %>% 
          hc_title(text = "") %>% 
          hc_yAxis(
            title = list(text = "")
            # title = list(text = "Hits", style = list(color = "white", fontFamily = "Roboto Slab"))
            #,labels = list(style = list(color = "white", fontFamily = "Roboto Slab"))
          ) %>%
          hc_xAxis(
            title = list(text = ""),
            #labels = list(style = list(color = "white", fontFamily = "Roboto Slab")),
            type = 'datetime',
            ordinal = FALSE
          )  %>%
          hc_colors(colors = "#7cb5ec85") %>% # "#F56B38"
          hc_size(height = 250) %>% 
          hc_tooltip(pointFormat = "{point.tooltip}")
      }
      
      columns_list <- list(
        ac_reg_new = colDef(
          width = 80,
          sticky = "left",
          style = list(cursor = "pointer"),
          headerStyle = list(cursor = "pointer")
        ),
        engine_position = colDef(
          width = 80,
          sticky = "left",
          style = list(cursor = "pointer"),
          headerStyle = list(cursor = "pointer")
        ), 
        engine_id = colDef(
          width = 80,
          sticky = "left",
          style = list(cursor = "pointer"),
          headerStyle = list(cursor = "pointer")
        )
      )
      
      for(parameter_name_flight_phase in colnames(params_nest_1)[4:ncol(params_nest_1)]){
        
        columns_list[[parameter_name_flight_phase]] <- colDef(
          name = parameter_name_flight_phase, 
          minWidth = 500, 
          align = "center",
          cell = function(value){
            if (is.null(value) == F) {
              create_plot(value)
            }
          }
        )
        
      }
      
      reactable(
        params_nest_1, 
        filterable = TRUE,
        # searchable = TRUE,
        resizable = TRUE,
        defaultPageSize = 5,
        showPageSizeOptions = T, 
        pageSizeOptions = c(5, 10, 25, 50, 100),
        highlight = T, 
        theme = reactableTheme(
          # backgroundColor = "#1D2024", color = "white", borderColor = "#666666",
          # paginationStyle = list(color = "white"), 
          # selectStyle = list(color = "black"),
          # headerStyle = list(color = "white", fontFamily = "Arial"),
          cellStyle = list(
            #color = "#FAFAFA", 
            fontFamily = "Source Code Pro, Consolas, Monaco, monospace", 
            fontSize = "14px"
          )
        ),
        columns = columns_list
      )
      
    }
    
  })
  
  output$fleetreports_dt_table <- DT::renderDataTable(server = FALSE,{
    
    req(fleetreports_data$params)
    
    if (is.null(fleetreports_data$params)){
      return()
    }
    else{
      browser()
      df <- fleetreports_data$params %>%
        group_by(
          ac_reg_new,
          ac_reg_old,
          aircraft_id,
          aircraft_type,
          engine_position,
          engine_type,
          engine_id,
          flight_phase,
          parameter_name
        ) %>%
        summarise(
          # min = round(min(float_value,na.rm = T),2),
          mean = round(mean(float_value,na.rm = T),2)
          # ,max = round(max(float_value,na.rm = T),2)
        ) %>%
        #mutate(row = row_number()) %>%
        tidyr::pivot_wider(
          # id_expand = TRUE,
          names_from = parameter_name,
          values_from = c(
            # min,
            mean
            # ,max
          )
        )
      
      df_aircraft <- fleetreports_data$params_aircraft %>%
        group_by(
          ac_reg_new,
          ac_reg_old,
          aircraft_id,
          aircraft_type,
          flight_phase,
          parameter_name
        ) %>%
        summarise(
          # min = round(min(float_value,na.rm = T),2),
          mean = round(mean(float_value,na.rm = T),2)
          # ,max = round(max(float_value,na.rm = T),2)
        ) %>%
        #mutate(row = row_number()) %>%
        tidyr::pivot_wider(
          # id_expand = TRUE,
          names_from = parameter_name,
          values_from = c(
            # min,
            mean
            # ,max
          )
        ) 
      
      browser()
      
      if(nrow(fleetreports_data$params) > 0){
        
        df_smooth <- fleetreports_data$params %>%
          group_by(
            ac_reg_new,
            ac_reg_old,
            aircraft_id,
            aircraft_type,
            engine_position,
            engine_type,
            engine_id,
            flight_phase,
            parameter_name
          ) %>%
          summarise(
            # min = round(min(float_value,na.rm = T),2),
            mean = round(mean(float_value_smooth,na.rm = T),2)
            # ,max = round(max(float_value,na.rm = T),2)
          ) %>%
          #mutate(row = row_number()) %>%
          tidyr::pivot_wider(
            # id_expand = TRUE,
            names_from = parameter_name,
            values_from = c(
              # min,
              mean
              # ,max
            )
          ) 
        
      
      
      for(col in setdiff(colnames(df_smooth), c(
        "ac_reg_new",
        "ac_reg_old",
        "aircraft_id",
        "aircraft_type",
        "engine_position",
        "engine_type",
        "engine_id",
        "flight_phase",
        "parameter_name"
      ))){
        
        colnames(df_smooth)[
          colnames(df_smooth) == col
          ] <- paste0(col,"_smooth")
        
      }
      
      if(nrow(df) > 0){
        
        if(input$rb_enable_smooth == 1){
          
          df <- df_smooth
          
        }
        else if(input$rb_enable_smooth == 3){
          
          df <- df %>%
            left_join(
              df_smooth,
              by = c(
                "ac_reg_new" = "ac_reg_new",
                "ac_reg_old" = "ac_reg_old",
                "aircraft_id" = "aircraft_id",
                "aircraft_type" = "aircraft_type",
                "engine_position" = "engine_position",
                "engine_type" = "engine_type",
                "engine_id" = "engine_id",
                "flight_phase" = "flight_phase"
              )
            )
        }
      }
        df <- df %>%
          left_join(
            df_aircraft,
            by = c(
              "ac_reg_new" = "ac_reg_new",
              "ac_reg_old" = "ac_reg_old",
              "aircraft_id" = "aircraft_id",
              "aircraft_type" = "aircraft_type",
              "flight_phase" = "flight_phase"
            )
          )
        
      }
      else{
        
        df <- df_aircraft
        
      }
      
      # DT::datatable({
      #   df
      # },
      # caption = "Report table",
      # extensions = 'Buttons',
      # 
      # options = list(
      #   dom = 'Bfrtip',
      #   
      #   buttons = list(
      #     list(
      #       extend = 'collection',  #'csv',
      #       buttons = c('csv', 'excel'),
      #       exportOptions = list(
      #         modifiers = list(page = "all")
      #       )
      #     )
      #   ),
      #   columnDefs=list(list(className='dt-center',targets="_all")
      #   ),
      #   scrollX = TRUE
      # ),
      # filter = "top",
      # selection = 'single',
      # # style = 'bootstrap',
      # class = 'hover', 
      # # class = 'cell-border stripe',
      # rownames = FALSE
      # )
      
      color_from_middle <- function (data, color1,color2) 
      {
        max_val=max(abs(data))
        JS(sprintf("isNaN(parseFloat(value)) || value < 0 ? 'linear-gradient(90deg, transparent, transparent ' + (50 + value/%s * 50) + '%%, %s ' + (50 + value/%s * 50) + '%%,%s  50%%,transparent 50%%)': 'linear-gradient(90deg, transparent, transparent 50%%, %s 50%%, %s ' + (50 + value/%s * 50) + '%%, transparent ' + (50 + value/%s * 50) + '%%)'",
                   max_val,color1,max_val,color1,color2,color2,max_val,max_val))
      }
      browser()
      dt <- DT::datatable({
        df
      },
      caption = "Fleet report",
      extensions = 'Buttons',
      options = list(
        paging = TRUE,
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
      
      for(i in 9:ncol(df)){
        
        dt <- dt %>%
          formatStyle(
            colnames(df)[i],
            background = color_from_middle(
              df[,i],
              'orange',
              'lightblue'
            ),
            backgroundSize = '100% 90%',
            backgroundRepeat = 'no-repeat',
            backgroundPosition = 'center'
          )
        
      }
      
      dt

    }
    
  })
  
  output$fleetreports_raw_data <- DT::renderDataTable(server = FALSE,{
    
    if (is.null(fleetreports_data$params)){
      return()
    }
    else{
      df <- fleetreports_data$params[,setdiff(
        colnames(
          fleetreports_data$params
        ),
        c(
          "parameter_name_flight_phase",
          "integer_value",
          "char_value"
        )
      )] %>%
        group_by(
          ac_reg_new,
          aircraft_id,
          aircraft_grp,
          engine_position,
          engine_id,
          engine_type,
          flight_phase,
          parameter_name,
          flight_datetime
        ) %>%
        mutate(row = row_number()) %>%
        tidyr::pivot_wider(
          names_from = parameter_name,
          values_from = c(
            float_value
          )
        ) %>%
        select(-row)
      
      df_aircraft <- fleetreports_data$params_aircraft[,setdiff(
        colnames(
          fleetreports_data$params_aircraft
        ),
        c(
          "parameter_name_flight_phase",
          "integer_value",
          "char_value"
        )
      )] %>%
        group_by(
          ac_reg_new,
          aircraft_id,
          aircraft_grp,
          flight_phase,
          parameter_name,
          flight_datetime
        ) %>%
        mutate(row = row_number()) %>%
        tidyr::pivot_wider(
          names_from = parameter_name,
          values_from = c(
            float_value
          )
        ) %>%
        select(-row)
      
      df <- df[!duplicated(df),]
      
      df_aircraft <- df_aircraft[!duplicated(df_aircraft),]
      
      if(nrow(df) > 0 & nrow(df_aircraft) > 0){
        
        df <- df %>%
          left_join(
            df_aircraft,
            by = c(
              "ac_reg_new" = "ac_reg_new",
              "ac_reg_old" = "ac_reg_old",
              "aircraft_id" = "aircraft_id",
              "aircraft_type" = "aircraft_type",
              "flight_phase" = "flight_phase",
              "flight_datetime" = "flight_datetime"
            )
          )
        
      }
      else if(nrow(df) == 0 & nrow(df_aircraft) > 0){
        
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
            extend = 'collection',  #'csv',
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
      # style = 'bootstrap',
      class = 'hover', 
      # class = 'cell-border stripe',
      rownames = FALSE
      )
    }
    
  })
  
  output$fleetreports_reportplot <- renderUI({
    
    req(fleetreports_data$preset)
    
    if (is.null(fleetreports_data$preset)){
      return()
    }
    else{
      fleetreportsVisualization(
        fleetsummary = fleetreports_data$fleetsummary,
        preset = fleetreports_data$preset,
        params = fleetreports_data$params,
        paramssmooth = NULL,
        params_aircraft = fleetreports_data$params_aircraft,
        color_engine = NULL
      )
    }
    
  })
  
  output$fleetreports_workspace <- renderUI({
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
                3,
                uiOutput(ns("fleetreport_operator"))
              ),
              column(
                3,
                uiOutput(ns("fleetreport_actype"))
              ),
              column(
                3,
                uiOutput(ns("fleetreport_acreg"))
              ),
              column(
                3,
                uiOutput(ns("fleetreport_presetname"))
              )
            )
          ),
          br(),
          column(1),
          column(
            3,
            hr(),
            fluidRow(
              uiOutput(ns("fleetreport_plotoptions")),
              br(),
              actionBttn(ns("update_fleetreport_data"), "Update report")
            )
          )
        )
      ),
      
      bs4TabCard(
        width = 12,
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Report table",
          withSpinner(DT::dataTableOutput(ns("fleetreports_dt_table")))
        ),
        tabPanel(
          title = "Report plot",
          actionBttn(ns("ab_export_fleetreports_preset"), "Download image"),
          br(),
          #withSpinner(uiOutput(ns("fleetreports_reportplot")))
          div(
            style = 'overflow-y:scroll;height:850px;',
            withSpinner(uiOutput(ns("fleetreports_reportplot")))
          )
        ),
        tabPanel(
          title = "Raw data",
          withSpinner(DT::dataTableOutput(ns("fleetreports_raw_data")))
        ),
        tabPanel(
          title = "Summary",
          withSpinner(reactableOutput(ns("fleetreports_table")))
        )
      )
    )
  })
  
  return(reactive({fleetreports_data}))
  
}